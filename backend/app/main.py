from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models as _models  # noqa: F401 - register ORM mappings
from app.config import APP_ENCRYPTION_KEY, APP_SECRET_KEY, CORS_ORIGINS
from app.database import Base, engine
from app.routers import aws_auth, auth_router, chat, vpc_starter


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if (
        not APP_SECRET_KEY
        or len(APP_SECRET_KEY) < 16
        or not APP_ENCRYPTION_KEY
        or len(APP_ENCRYPTION_KEY.strip()) < 10
    ):
        raise RuntimeError(
            "Set APP_SECRET_KEY (16+ chars) and APP_ENCRYPTION_KEY (Fernet key) "
            "in backend .env — see .env.example."
        )
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Cloud Deployment Assistant API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(aws_auth.router)
app.include_router(chat.router)
app.include_router(vpc_starter.router)
