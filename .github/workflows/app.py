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

# Utilisation de st.secrets pour stocker les informations
# Lors du déploiement sur Streamlit Cloud, vous devrez définir ces secrets.
# Voir la section "Configuration pour Streamlit Cloud" ci-dessous.
try:
    DRIVE_FOLDER_ID = st.secrets["google"]["DRIVE_FOLDER_ID"]
except KeyError:
    st.error("L'ID du dossier Google Drive n'est pas configuré dans st.secrets.")
    DRIVE_FOLDER_ID = None

# --- Fonctions d'Authentification et de Service ---

@st.cache_resource
def get_drive_service():
    # ... (code précédent)

    # 1. Charger les credentials (depuis un fichier si local, ou secrets si déployé)
    if os.path.exists(CREDENTIALS_FILE):
        # ... (gestion locale)
    elif "google" in st.secrets:
        # --- NOUVELLE VÉRIFICATION AMÉLIORÉE ---
        required_keys = ["client_id", "client_secret", "project_id", "auth_uri", "token_uri", "auth_provider_x509_cert_url"]
        
        missing_keys = [k for k in required_keys if k not in st.secrets["google"]]
        
        if missing_keys:
            st.error(f"❌ Erreur de configuration dans `st.secrets` : Les clés Google Drive suivantes sont manquantes ou mal orthographiées : {', '.join(missing_keys)}. Veuillez vérifier la section [google].")
            return None # Arrêter ici
        # --- FIN DE LA VÉRIFICATION AMÉLIORÉE ---

        # Construit l'objet à partir des secrets
        client_config = {
            "installed": {
                "client_id": st.secrets["google"]["client_id"],
                "client_secret": st.secrets["google"]["client_secret"],
                "project_id": st.secrets["google"]["project_id"],
                "auth_uri": st.secrets["google"]["auth_uri"],
                "token_uri": st.secrets["google"]["token_uri"],
                "auth_provider_x509_cert_url": st.secrets["google"]["auth_provider_x509_cert_url"],
                "redirect_uris": st.secrets["google"]["redirect_uris"]
            }
        }
    else:
        st.error(f"Fichier '{CREDENTIALS_FILE}' non trouvé et section 'google' manquante dans st.secrets.")
        return None

    # ... (reste du code)

    # 2. Charger les jetons (depuis un fichier si local, ou secrets si déployé)
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    elif "google" in st.secrets and "token_json" in st.secrets["google"]:
        creds_info = json.loads(st.secrets["google"]["token_json"])
        creds = Credentials.from_authorized_user_info(creds_info, SCOPES)

    # 3. Gérer l'expiration ou le manque de jeton
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            st.info("Jeton expiré. Tentative de rafraîchissement...")
            try:
                creds.refresh(Request())
            except Exception as e:
                st.error(f"Erreur lors du rafraîchissement du jeton. Vous devez vous ré-authentifier : {e}")
                # Forcer la ré-authentification si le rafraîchissement échoue
                creds = None
        
        if not creds:
            # Cette partie nécessite une manipulation pour une app déployée
            # En local, vous pouvez toujours utiliser flow.run_local_server()
            # Pour un déploiement sécurisé, la meilleure pratique est de réaliser 
            # l'authentification *une fois* en local, puis de copier le token.json 
            # dans les secrets de l'application déployée.
            st.warning("""
            Authentification requise ! 
            Pour un déploiement Streamlit Cloud, vous devez réaliser l'authentification 
            en local une fois, puis copier le contenu du fichier `token.json` 
            dans `st.secrets` (clé `token_json`).
            """)
            st.stop() # Arrête l'exécution de l'application
            
    # 4. Enregistrement du jeton mis à jour (localement ou affichage pour secrets)
    if os.path.exists(TOKEN_FILE) or "token_json" not in st.secrets["google"]:
        # Sauvegarde locale du jeton rafraîchi (pour les tests en local)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    else:
        # Affiche le nouveau jeton rafraîchi pour le mettre à jour dans Streamlit Cloud
        st.code(creds.to_json(), language="json", label="Nouveau token.json à mettre à jour dans st.secrets")

    return build('drive', 'v3', credentials=creds)

# --- Fonctions Drive (Adaptées pour Streamlit) ---

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

        st.success(f"**{len(items)}** fichiers trouvés :")
        # Affichage des résultats dans un tableau
        st.table([{'Nom': item['name'], 'ID': item['id'], 'Type': item['mimeType']} for item in items])

    except Exception as error:
        st.error(f'⚠️ Une erreur est survenue lors du listage : {error}')

def uploader_fichier(service, uploaded_file, folder_id):
    """
    Uploade un objet Streamlit UploadedFile vers Google Drive.
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
        
        # 2. Créer l'objet MediaFileUpload à partir du flux de données
        # On utilise MediaIoBaseUpload car nous avons un flux en mémoire (BytesIO)
        # plutôt qu'un chemin de fichier local.
        
        # On lit le flux de données en mémoire
        file_bytes = uploaded_file.read()
        media_stream = BytesIO(file_bytes)

        media = MediaFileUpload(
            media_stream, 
            mimetype=uploaded_file.type, # Utilise le mimeType de Streamlit
            resumable=True
        )

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
    st.title("☁️ Google Drive Uploader Streamlit")
    st.write("Cet outil permet d'uploader un fichier vers un dossier spécifique de Google Drive et d'en lister le contenu.")
    
    # 1. Obtient le service authentifié (mise en cache)
    drive_service = get_drive_service()

    if drive_service:
        # 2. Section Upload
        uploaded_file = st.file_uploader(
            "Choisissez un fichier à uploader (max 200MB)",
            type=None # Autorise tous les types de fichiers
        )
        
        if uploaded_file is not None:
            # Bouton d'upload explicite
            if st.button("Lancer l'Upload vers Drive"):
                uploader_fichier(drive_service, uploaded_file, DRIVE_FOLDER_ID)
                
                # Re-lister après l'upload
                st.divider()
                lister_fichiers_dossier(drive_service, DRIVE_FOLDER_ID)
                
        # 3. Section Liste (si pas d'upload en cours)
        if uploaded_file is None:
            st.divider()
            if st.button("Lister les fichiers du dossier Drive"):
                lister_fichiers_dossier(drive_service, DRIVE_FOLDER_ID)
                
    else:
        st.warning("Veuillez configurer correctement l'authentification Google Drive.")

if __name__ == '__main__':
    main()
