"""Password hashing and signed session tokens."""

import hmac

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

from app.config import APP_SECRET_KEY, SESSION_MAX_AGE_SECONDS

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, password_hash: str) -> bool:
    return pwd_context.verify(plain, password_hash)


def _serializer() -> URLSafeTimedSerializer:
    if not APP_SECRET_KEY or len(APP_SECRET_KEY) < 16:
        raise RuntimeError(
            "APP_SECRET_KEY must be set in .env (at least 16 characters) for login sessions."
        )
    return URLSafeTimedSerializer(APP_SECRET_KEY, salt="cda-user-session")


def create_session_token(user_id: int) -> str:
    return _serializer().dumps({"uid": user_id})


def decode_session_token(token: str) -> int | None:
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        uid = data.get("uid")
        if isinstance(uid, int) and uid > 0:
            return uid
        return None
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
