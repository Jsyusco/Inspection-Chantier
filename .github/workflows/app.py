import streamlit as st
import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from io import BytesIO

# --- Configuration et Constantes ---
SCOPES = ['https://www.googleapis.com/auth/drive']
TOKEN_FILE = 'token.json'
CREDENTIALS_FILE = 'credentials.json'

# --- Fonctions d'Authentification et de Service ---

# Liste des clés nécessaires pour reconstruire les credentials Google Drive
REQUIRED_CREDENTIALS_KEYS = [
    "client_id", 
    "client_secret", 
    "project_id", 
    "auth_uri", 
    "token_uri", 
    "auth_provider_x509_cert_url",
    "redirect_uris" # Souvent une liste, mais on vérifie la clé d'existence
]

@st.cache_resource
def get_drive_service():
    """
    Gère l'authentification et retourne l'objet service Drive.
    Utilise 'token.json' et 'credentials.json' en local, ou st.secrets en production.
    """
    st.info("🔄 Tentative de récupération du service Google Drive...")
    
    client_config = None
    
    # 1. Charger les credentials (depuis un fichier local ou st.secrets)
    if os.path.exists(CREDENTIALS_FILE):
        # Authentification Locale (développement)
        st.info("Mode local : Utilisation de credentials.json.")
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                client_config = json.load(f)
        except Exception as e:
            st.error(f"Erreur de lecture de {CREDENTIALS_FILE}: {e}")
            return None
    elif "google" in st.secrets:
        # Authentification Déployée (Streamlit Cloud)
        st.info("Mode cloud : Utilisation de st.secrets.")
        
        # Vérification des clés de configuration pour éviter KeyError
        missing_keys = [k for k in REQUIRED_CREDENTIALS_KEYS if k not in st.secrets["google"]]
        
        if missing_keys:
            st.error(f"❌ Erreur de configuration dans `st.secrets` : Les clés Google Drive suivantes sont manquantes ou mal orthographiées : **{', '.join(missing_keys)}** dans la section [google].")
            return None
            
        # Construction de l'objet credentials à partir des secrets
        client_config = {
            "installed": { # Assumons le type "installed" comme dans le code original
                k: st.secrets["google"][k] for k in REQUIRED_CREDENTIALS_KEYS
            }
        }
    else:
        st.error(f"Fichier '{CREDENTIALS_FILE}' non trouvé et section 'google' manquante dans st.secrets. Veuillez configurer l'authentification.")
        return None

    # 2. Charger les jetons d'accès et de rafraîchissement
    creds = None
    # Tentative de chargement depuis 'token.json' (local)
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    # Tentative de chargement depuis st.secrets (cloud)
    elif "google" in st.secrets and "token_json" in st.secrets["google"]:
        try:
            creds_info = json.loads(st.secrets["google"]["token_json"])
            creds = Credentials.from_authorized_user_info(creds_info, SCOPES)
        except Exception as e:
            st.error(f"Erreur lors du décodage de 'token_json' dans st.secrets: {e}")
            return None

    # 3. Gérer l'expiration ou le manque de jeton
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            st.warning("Jeton expiré. Tentative de rafraîchissement...")
            try:
                creds.refresh(Request())
            except Exception as e:
                st.error(f"🛑 Erreur lors du rafraîchissement du jeton. Jeton de rafraîchissement invalide/manquant : {e}")
                creds = None # Forcer la ré-authentification/le message d'erreur
        
        if not creds:
            st.error("""
            **Authentification requise !** Pour un déploiement Streamlit Cloud, vous devez réaliser l'authentification 
            en local une fois, puis copier le contenu complet du fichier `token.json` 
            dans `st.secrets` (clé `token_json`).
            """)
            return None # Arrêter ici
            
# 4. Enregistrement/Affichage du jeton mis à jour
    # Si nous sommes en mode local ou si le token_json n'a pas été défini (cas initial)
    if os.path.exists(TOKEN_FILE):
        # Sauvegarde locale du jeton rafraîchi (pour les tests en local)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    elif "google" in st.secrets and "token_json" in st.secrets["google"] and creds and creds.valid:
        # Affiche le nouveau jeton rafraîchi (si l'app est déployée et que le refresh a fonctionné)
        st.code(creds.to_json(), language="json", label="✅ Nouveau token.json rafraîchi (Copiez ceci dans st.secrets pour la persistance)")

    return build('drive', 'v3', credentials=creds)

# --- Fonctions Drive (Adaptées pour Streamlit) ---

def lister_fichiers_dossier(service, folder_id):
    """Liste les fichiers d'un dossier Google Drive spécifique et affiche dans Streamlit."""
    if not folder_id:
        return
    
    st.subheader("📁 Fichiers dans le dossier Google Drive")
    try:
        # La requête de recherche: fichiers dans le dossier (ID) et non dans la corbeille.
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
        # Affichage des résultats dans un tableau
        st.dataframe([{'Nom': item['name'], 'ID': item['id'], 'Type': item['mimeType']} for item in items])

    except Exception as error:
        st.error(f'⚠️ Une erreur est survenue lors du listage : {error}')

def uploader_fichier(service, uploaded_file, folder_id):
    """
    Uploade un objet Streamlit UploadedFile vers Google Drive en utilisant MediaIoBaseUpload.
    """
    if not folder_id or not uploaded_file:
        return
        
    st.subheader("⬆️ Upload du fichier")
    try:
        # 1. Définir les métadonnées du fichier
        file_metadata = {
            'name': uploaded_file.name,
            'parents': [folder_id]
        }
        
        # 2. Créer l'objet MediaFileUpload
        # On lit le flux de données en mémoire (BytesIO)
        file_bytes = uploaded_file.read()
        media_stream = BytesIO(file_bytes)

        # Utilisation de MediaFileUpload mais en fournissant un flux BytesIO
        media = MediaFileUpload(
            media_stream, 
            mimetype=uploaded_file.type if uploaded_file.type else 'application/octet-stream', 
            resumable=True
        )
        
        # Le nom du fichier est déjà défini dans file_metadata, MediaFileUpload déduit le type MIME
        
        # 3. Appel de l'API pour créer le fichier
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
    st.write("Cet outil permet d'uploader un fichier vers un dossier spécifique de Google Drive et d'en lister le contenu, en utilisant `st.secrets` pour l'authentification.")

    # Récupération de l'ID du dossier
    try:
        drive_folder_id = st.secrets["google"]["DRIVE_FOLDER_ID"]
    except (KeyError, AttributeError):
        st.error("L'ID du dossier Google Drive (`DRIVE_FOLDER_ID`) n'est pas configuré dans `st.secrets`.")
        drive_folder_id = None
        
    # 1. Obtient le service authentifié (mise en cache)
    drive_service = get_drive_service()

    if drive_service and drive_folder_id:
        st.divider()
        # 2. Section Upload
        uploaded_file = st.file_uploader(
            "Choisissez un fichier à uploader",
            type=None # Autorise tous les types de fichiers
        )
        
        if uploaded_file is not None:
            # Bouton d'upload explicite
            if st.button(f"🚀 Lancer l'Upload de {uploaded_file.name} vers Drive"):
                uploader_fichier(drive_service, uploaded_file, drive_folder_id)
                
                # Re-lister après l'upload
                st.divider()
                lister_fichiers_dossier(drive_service, drive_folder_id)
                
        # 3. Section Liste 
        st.divider()
        if st.button("Actualiser la liste des fichiers Drive"):
            lister_fichiers_dossier(drive_service, drive_folder_id)
                
    else:
        st.warning("Veuillez résoudre les erreurs de configuration ci-dessus pour continuer.")

if __name__ == '__main__':
    main()
