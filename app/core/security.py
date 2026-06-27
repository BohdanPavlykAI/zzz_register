from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.core.config import settings

fernet = Fernet(settings.SURNAME_ENCRYPTION_KEY.encode())


# ── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


# ── Surname encryption ────────────────────────────────────────────────────────

def encrypt_surname(surname: str) -> bytes:
    return fernet.encrypt(surname.encode())


def decrypt_surname(data: bytes) -> str:
    return fernet.decrypt(data).decode()