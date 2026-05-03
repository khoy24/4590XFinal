"""User registration, login, logout."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS
from app.database import get_db
from app.deps import get_current_user, get_current_user_optional
from app.models import User
from app.security import create_session_token, hash_password, verify_password
from app.services.credential_manager import clear_user_credential_cache
from app.state import clear_user_workspace

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: int
    email: str

    model_config = {"from_attributes": True}


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,  # set True behind HTTPS in production
        path="/",
    )


@router.post("/register", response_model=UserOut)
def register(
    body: RegisterRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    existing = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")
    password_hash = hash_password(body.password)
    user = User(email=body.email.lower().strip(), password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_session_token(user.id)
    _set_session_cookie(response, token)
    return user


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    email = body.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_session_token(user.id)
    _set_session_cookie(response, token)
    return user


@router.post("/logout")
def logout(
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
):
    clear_user_credential_cache(user.id)
    clear_user_workspace(user.id)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me", response_model=UserOut | None)
def me(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User | None:
    return user
