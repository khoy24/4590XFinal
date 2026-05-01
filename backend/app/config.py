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

CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
