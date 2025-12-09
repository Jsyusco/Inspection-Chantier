# --- FONCTION D'INITIALISATION GOOGLE DRIVE (MISE À JOUR) ---

@st.cache_resource(show_spinner="Initialisation de Google Drive...")
def init_google_drive():
    # ... (Vérifications d'importation omises pour la concision) ...

    try:
        # Reconstruire l'objet JSON du compte de service à partir des secrets individuels
        # Les clés proviennent directement du secrets.toml que vous avez fourni
        json_key_info = {
            "type": st.secrets["google_drive"]["type"],
            "project_id": st.secrets["google_drive"]["project_id"],
            "private_key_id": st.secrets["google_drive"]["private_key_id"],
            "private_key": st.secrets["google_drive"]["private_key"], # Utilise la clé échappée
            "client_email": st.secrets["google_drive"]["client_email"],
            "client_id": st.secrets["google_drive"]["client_id"],
            "auth_uri": st.secrets["google_drive"]["auth_uri"],
            "token_uri": st.secrets["google_drive"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["google_drive"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["google_drive"]["client_x509_cert_url"],
            "universe_domain": st.secrets["google_drive"].get("universe_domain", "googleapis.com")
        }

        # 1. Création des identifiants (Plus besoin de clean_json_string ou json.loads)
        creds = service_account.Credentials.from_service_account_info(
            json_key_info,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        
        http_auth = AuthorizedSession(creds)
        drive = GoogleDrive(http_auth)
        
        # 2. Récupération de l'ID du dossier cible
        folder_id = st.secrets["google_drive"]["target_folder_id"] # Clé requise
        
        # ... (Vérification et succès omis pour la concision) ...
        st.success("✅ Google Drive initialisé avec succès. Prêt à uploader.")
        return drive, folder_id

    except Exception as e:
        # ... (Gestion des erreurs omise) ...
        st.error(f"❌ ÉCHEC de l'initialisation de Google Drive : {e}")
        st.caption("Veuillez vérifier les valeurs individuelles de votre compte de service dans `secrets.toml`.")
        return None, None
