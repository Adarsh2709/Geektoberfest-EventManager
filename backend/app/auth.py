import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    )
    return jwt.encode({"sub": str(user_id), "exp": expires}, _secret_key(), algorithm="HS256")


def _secret_key() -> str:
    key = os.getenv("SECRET_KEY", "")
    if not key:
        raise RuntimeError("SECRET_KEY must be set in backend/.env")
    return key


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign in to use this endpoint",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, _secret_key(), algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError, RuntimeError):
        raise unauthorized
    user = db.get(User, user_id)
    if not user:
        raise unauthorized
    return user
