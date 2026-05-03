"""Encrypt sensitive fields at rest (IAM Role ARN)."""

from cryptography.fernet import Fernet

from app.config import APP_ENCRYPTION_KEY

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not APP_ENCRYPTION_KEY:
            raise RuntimeError(
                "APP_ENCRYPTION_KEY is not set. Generate one with: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        key = APP_ENCRYPTION_KEY.strip().encode()
        _fernet = Fernet(key)
    return _fernet


def encrypt_str(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_str(blob: str) -> str:
    return _get_fernet().decrypt(blob.encode()).decode()
