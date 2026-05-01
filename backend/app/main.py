from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.routers import aws_auth, chat, vpc_starter

app = FastAPI(title="Cloud Deployment Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(aws_auth.router)
app.include_router(chat.router)
app.include_router(vpc_starter.router)
