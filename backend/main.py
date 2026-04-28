# /backend/main.py
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from dotenv import load_dotenv

# load environment variables from .env file
load_dotenv()

# configure Gemini API
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY is missing from the .env file")

genai.configure(api_key=gemini_api_key)

# right now use gemini-1.5-flash as it is fast and cheap
model = genai.GenerativeModel('gemini-1.5-flash') 

# initialize FastAPI App
app = FastAPI(title="Cloud Deployment Assistant API")

# setup CORS (Cross-Origin Resource Sharing)
# This allows your React frontend (running on a different port) to talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"], # Add your frontend URL here
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# define Data Models
# ensures FastAPI knows what data structure to expect from the frontend
class ChatRequest(BaseModel):
    prompt: str

class ChatResponse(BaseModel):
    reply: str

# define API Endpoints
@app.post("/chat", response_model=ChatResponse)
async def chat_with_gemini(request: ChatRequest):
    try:
        # give the model system instructions
        # future ask for output in JSON / other
        system_prompt = (
            "You are a Cloud Security Architect helping a non-technical user "
            "deploy AWS infrastructure securely. Keep your answers brief, friendly, "
            "and easy to understand."
        )
        
        full_prompt = f"{system_prompt}\n\nUser Request: {request.prompt}"
        
        # call the Gemini API
        response = model.generate_content(full_prompt)
        
        return ChatResponse(reply=response.text)
        
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error while generating response.")

@app.get("/")
async def health_check():
    return {"status": "Backend is running!"}