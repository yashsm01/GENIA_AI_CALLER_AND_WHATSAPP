"""
api/auth.py — JWT Authentication endpoints.

Routes:
  POST /api/auth/register  - Create a new user account
  POST /api/auth/login     - Authenticate, receive JWT access token
  GET  /api/auth/me        - Get current user profile (requires token)
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr

from database.models import User
from database import sqlite_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ─── Config ───────────────────────────────────────────────────────────────────
_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production-please")
_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ─── Schemas ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    company_name: str = "My Company"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str
    email: str


class UserProfile(BaseModel):
    id: str
    name: str
    email: str
    company_name: str
    twilio_phone: str
    default_language: str
    is_active: bool


import hashlib

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _hash_password(plain: str) -> str:
    # Use SHA256 pre-hash to avoid bcrypt's 72-byte limit
    p = hashlib.sha256(plain.encode()).hexdigest()
    return _pwd_ctx.hash(p)


def _verify_password(plain: str, hashed: str) -> bool:
    p = hashlib.sha256(plain.encode()).hexdigest()
    return _pwd_ctx.verify(p, hashed)


def _create_access_token(user_id: str, email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Dependency: Decode JWT and return the authenticated User document."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await User.get(user_id)
    if not user or not user.is_active:
        raise credentials_exception
    return user


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
    """Create a new user account."""
    existing = await User.find_one(User.email == req.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")

    user = User(
        name=req.name,
        email=req.email,
        hashed_password=_hash_password(req.password),
        company_name=req.company_name,
    )
    await user.insert()
    logger.info("[Auth] New user registered: %s", req.email)

    token = _create_access_token(str(user.id), user.email)
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        name=user.name,
        email=user.email,
    )


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    """Authenticate with email + password, receive JWT."""
    user = await User.find_one(User.email == form.username)
    if not user or not _verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    token = _create_access_token(str(user.id), user.email)
    logger.info("[Auth] Login: %s", user.email)
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        name=user.name,
        email=user.email,
    )


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the current logged-in user's profile."""
    return UserProfile(
        id=str(current_user.id),
        name=current_user.name,
        email=current_user.email,
        company_name=current_user.company_name,
        twilio_phone=current_user.twilio_phone,
        default_language=current_user.default_language,
        is_active=current_user.is_active,
    )
