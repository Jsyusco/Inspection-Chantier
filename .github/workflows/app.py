# --- IMPORTS ET PRÉPARATION ---
import streamlit as st
import io
import json
import re
from datetime import datetime
import os

# Importation spécifique pour Google Drive
try:
    # Nécessaire pour pydrive2
    from pydrive2.auth import GoogleAuth
    from pydrive2.drive import GoogleDrive
    from google.oauth2 import service_account # Import utilisé dans l'initialisation
    from google.auth.transport.requests import AuthorizedSession # <--- Import de l'objet non compatible
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    # Ce message d'erreur s'affiche si les dépendances ne sont pas installées.
    st.error("🚨 Erreur: Le module 'pydrive2' ou ses dépendances sont manquants. Exécutez 'pip install pydrive2 google-api-python-client'.")
    GOOGLE_DRIVE_AVAILABLE = False
    
# --- CONFIGURATION ET STYLE ---
st.set_page_config(page_title="Test Google Drive", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #121212; color: #e0e0e0; }
    .main-header { background-color: #1e1e1e; padding: 20px; border-radius: 10px; margin-bottom: 20px; text-align: center; border-bottom: 3px solid #63B3ED; }
    .phase-block { background-color: #1e1e1e; padding: 25px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #333; }
    .stSuccess, .stError, .stWarning { border-radius: 8px; padding: 10px; }
</style>
""", unsafe_allow_html=True)

# --- FONCTION DE NETTOYAGE AMÉLIORÉE POUR LA ROBUSTESSE ---
def clean_json_string(json_string):
    """
    Nettoie la chaîne JSON pour supprimer les caractères de contrôle non valides.
    """
    if not isinstance(json_string, str):
        return json_string
        
    # Pattern : remplace tout ce qui n'est pas un caractère imprimable ASCII (\x20-\x7E)
    # ou un caractère de contrôle "sûr" (\t, \n, \r) par une chaîne vide.
    cleaned_string = re.sub(r'[^\x20-\x7E\t\n\r]', '', json_string)
    return cleaned_string

# --- FONCTION D'INITIALISATION GOOGLE DRIVE (INITIALE - CAUSE DU BUG) ---

@st.cache_resource(show_spinner="Initialisation de Google Drive...")
def init_google_drive():
    try:
        # Reconstruire l'objet JSON du compte de service à partir des secrets individuels
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

        # 1. Création des identifiants (Utilisation de google.oauth2.service_account)
        creds = service_account.Credentials.from_service_account_info(
            json_key_info
    
