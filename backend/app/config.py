import os

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY is missing from the .env file")

genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel("gemini-2.5-flash")

BACKEND_ACCOUNT_ID = os.getenv("AWS_BACKEND_ACCOUNT_ID")
if not BACKEND_ACCOUNT_ID:
    print("WARNING: AWS_BACKEND_ACCOUNT_ID is missing from .env. The link will not work.")

# added the ngrok webhook for the lambda call to auto fill-in the ARN 
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN")
if not WEBHOOK_DOMAIN:
    print("WARNING: WEBHOOK_DOMAIN is missing. Auto-webhook will fail. Use ngrok for local dev.")

CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]

# Persistent app data (SQLite by default)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# Required for signed login cookies (generate: python -c "import secrets; print(secrets.token_hex(32))")
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY")
# Fernet key for encrypting Role ARNs at rest (generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
APP_ENCRYPTION_KEY = os.getenv("APP_ENCRYPTION_KEY")

SESSION_COOKIE_NAME = "cda_session"
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(60 * 60 * 24 * 7)))
