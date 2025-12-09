import streamlit as st
import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from io import BytesIO

# --- Configuration et Constantes ---
SCOPES = ['https://www.googleapis.com/auth/drive']
TOKEN_FILE = 'token.json'
CREDENTIALS_FILE = 'credentials.json'

# Liste des clés nécessaires pour reconstruire les credentials Google Drive
REQUIRED_CREDENTIALS_KEYS = [
    "client_id", 
    "client_secret", 
    "project_id", 
    "auth_uri", 
    "token_uri", 
    "auth_provider_x509_cert_url",
    "redirect_uris"
]

# --- Fonctions d'Authentification et de Service ---

@st.cache_resource
def get_drive_service():
    """
    Gère l'authentification et retourne l'objet service Drive.
    Utilise 'token.json' et 'credentials.json' en local, ou st.secrets en production.
    """
    st.info("🔄 Tentative de récupération du service Google Drive...")
    
    client_config = None
    
    # 1. Chargement des credentials (local vs. secrets)
    if os.path.exists(CREDENTIALS_FILE):
        st.info("Mode local : Utilisation de credentials.json.")
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                client_config = json.load(f)
        except Exception as e:
            st.error(f"Erreur de lecture de {CREDENTIALS_FILE}: {e}")
            return None
    elif "google" in st.secrets:
        st.info("Mode cloud : Utilisation de st.secrets.")
        
        # Vérification des clés de configuration pour éviter KeyError
        missing_keys = [k for k in REQUIRED_CREDENTIALS_KEYS if k not in st.secrets["google"]]
        
        if missing_keys:
            st.error(f"❌ Erreur de configuration dans `st.secrets` : Les clés Google Drive suivantes sont manquantes ou mal orthographiées : **{', '.join(missing_keys)}** dans la section [google].")
            return None
            
        # Construction de l'objet credentials à partir des secrets
        client_config = {
            "installed": {
                k: st.secrets["google"][k] for k in REQUIRED_CREDENTIALS_KEYS
            }
        }
    else:
        st.error(f"Fichier '{CREDENTIALS_FILE}' non trouvé et section 'google' manquante dans st.secrets. Veuillez configurer l'authentification.")
        return None

    # 2. Chargement des jetons d'accès et de rafraîchissement
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    elif "google" in st.secrets and "token_json" in st.secrets["google"]:
        try:
            creds_info = json.loads(st.secrets["google"]["token_json"])
            creds = Credentials.from_authorized_user_info(creds_info, SCOPES)
        except Exception as e:
            st.error(f"Erreur lors du décodage de 'token_json' dans st.secrets. Vérifiez le format JSON : {e}")
            return None

    # 3. Gérer l'expiration ou le manque de jeton
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            st.warning("Jeton expiré. Tentative de rafraîchissement...")
            try:
                creds.refresh(Request())
            except Exception as e:
                st.error(f"🛑 Erreur lors du rafraîchissement. Jeton invalide ou non présent dans secrets : {e}")
                creds = None
        
        if not creds:
            st.error("""
            **Authentification requise !** Pour un déploiement Streamlit Cloud, vous devez réaliser l'authentification 
            en local une fois, puis copier le contenu complet du fichier `token.json` 
            dans `st.secrets` (clé `token_json`).
            """)
            return None
            
    # 4. Enregistrement/Affichage du jeton mis à jour (Correction du TypeError)
    if creds and creds.valid:
        if os.path.exists(TOKEN_FILE):
            # Sauvegarde locale du jeton rafraîchi
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        elif "google" in st.secrets and "token_json" in st.secrets["google"]:
            # Affiche le nouveau jeton rafraîchi pour la mise à jour des secrets
            # On s'assure que creds est valide pour éviter le TypeError.
            st.code(creds.to_json(), language="json", label="✅ Nouveau token.json rafraîchi (Copiez ceci dans st.secrets pour la persistance)")
    
    # On retourne le service s'il a été construit avec succès
    if creds and creds.valid:
        return build('drive', 'v3', credentials=creds)
    else:
        return None

# --- Fonctions Drive ---

def lister_fichiers_dossier(service, folder_id):
    """Liste les fichiers d'un dossier Google Drive spécifique et affiche dans Streamlit."""
    if not folder_id:
        return
    
    st.subheader("📁 Fichiers dans le dossier Google Drive")
    try:
        query = f"'{folder_id}' in parents and trashed = false"

        results = service.files().list(
            q=query,
            pageSize=50,
            fields="nextPageToken, files(id, name, mimeType, size)"
        ).execute()

        items = results.get('files', [])

        if not items:
            st.info('Aucun fichier trouvé dans ce dossier.')
            return

        st.success(f"**{len(items)}** fichiers trouvés dans le dossier.")
        st.dataframe([{'Nom': item['name'], 'ID': item['id'], 'Type': item['mimeType']} for item in items])

    except Exception as error:
        st.error(f'⚠️ Une erreur est survenue lors du listage : {error}')

def uploader_fichier(service, uploaded_file, folder_id):
    """
    Uploade un objet Streamlit UploadedFile vers Google Drive en utilisant MediaFileUpload
    avec un flux BytesIO.
    """
    if not folder_id or not uploaded_file:
        return
        
    st.subheader("⬆️ Upload du fichier")
    try:
        file_metadata = {
            'name': uploaded_file.name,
            'parents': [folder_id]
        }
        
        # Lecture du flux de données en mémoire
        file_bytes = uploaded_file.read()
        media_stream = BytesIO(file_bytes)

        media = MediaFileUpload(
            media_stream, 
            mimetype=uploaded_file.type if uploaded_file.type else 'application/octet-stream', 
            resumable=True
        )

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name'
        ).execute()

        st.success(f"✅ Fichier uploadé avec succès : **{file.get('name')}** (ID: {file.get('id')})")
        st.balloons()
        
    except Exception as error:
        st.error(f"❌ Une erreur est survenue lors de l'upload : {error}")

# --- Application Streamlit Principale ---

def main():
    st.title("☁️ Google Drive Uploader Streamlit Sécurisé")
    st.write("Cet outil permet d'uploader un fichier vers un dossier spécifique de Google Drive en utilisant `st.secrets` pour l'authentification.")

    # Récupération de l'ID du dossier
    drive_folder_id = None
    try:
        if "google" in st.secrets and "DRIVE_FOLDER_ID" in st.secrets["google"]:
            drive_folder_id = st.secrets["google"]["DRIVE_FOLDER_ID"]
        else:
            st.error("L'ID du dossier Google Drive (`DRIVE_FOLDER_ID`) n'est pas configuré dans la section [google] de `st.secrets`.")
    except Exception:
        # Gère le cas où st.secrets n'est pas du tout un dictionnaire
        st.error("Erreur de lecture de st.secrets.")
        
    # 1. Obtient le service authentifié
    drive_service = get_drive_service()

    if drive_service and drive_folder_id:
        st.divider()
        st.success(f"Connecté à Google Drive. ID du dossier cible : **{drive_folder_id}**")
        
        # 2. Section Upload
        uploaded_file = st.file_uploader(
            "Choisissez un fichier à uploader",
            type=None
        )
        
        if uploaded_file is not None:
            if st.button(f"🚀 Lancer l'Upload de {uploaded_file.name} vers Drive"):
                uploader_fichier(drive_service, uploaded_file, drive_folder_id)
                
                st.divider()
                lister_fichiers_dossier(drive_service, drive_folder_id)
                
        # 3. Section Liste 
        st.divider()
        if st.button("Actualiser la liste des fichiers Drive"):
            lister_fichiers_dossier(drive_service, drive_folder_id)
                
    elif not drive_service:
        st.warning("L'application ne peut pas se connecter à Google Drive. Veuillez vérifier les messages d'erreur et la configuration `st.secrets`.")

if __name__ == '__main__':
    main()
