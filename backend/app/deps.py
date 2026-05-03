"""FastAPI dependencies: DB session, current user, AWS-connected user."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SESSION_COOKIE_NAME
from app.database import get_db
from app.models import AwsConnection, User
from app.security import decode_session_token


def get_optional_token(
    request: Request,
    cookie_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> str | None:
    """Allow session token from Cookie or Authorization: Bearer (for API clients)."""
    if cookie_token:
        return cookie_token
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None
    return None


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Depends(get_optional_token)],
) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user_id = decode_session_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return user


def get_current_user_optional(
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Depends(get_optional_token)],
) -> User | None:
    if not token:
        return None
    user_id = decode_session_token(token)
    if user_id is None:
        return None
    return db.get(User, user_id)


def get_active_aws_connection(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AwsConnection:
    conn = db.scalar(
        select(AwsConnection).where(AwsConnection.user_id == user.id),
    )
    if not conn or conn.connect_status != "active":
        raise HTTPException(
            status_code=401,
            detail="AWS is not connected. Complete CloudFormation setup and verify.",
        )
    return conn
