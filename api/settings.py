"""
api/settings.py — User settings & credential management.

Routes:
  GET  /api/settings          - Get current user's settings
  PUT  /api/settings          - Save all settings (syncs to SQLite hot cache)
  PUT  /api/settings/password - Change password
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database.models import User
from database import sqlite_manager
from api.auth import get_current_user, _hash_password, _verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    # Company profile
    name: Optional[str] = None
    company_name: Optional[str] = None
    default_language: Optional[str] = None
    voice_mode: Optional[str] = None

    # Twilio credentials
    twilio_phone: Optional[str] = None
    twilio_sid: Optional[str] = None
    twilio_token: Optional[str] = None
    whatsapp_number: Optional[str] = None

    # AI credentials
    openai_key: Optional[str] = None
    elevenlabs_key: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    elevenlabs_agent_id: Optional[str] = None

    # SMTP (for email delivery)
    smtp_host: Optional[str] = None
    smtp_port: Optional[str] = None
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None


class SettingsResponse(BaseModel):
    name: str
    company_name: str
    email: str
    twilio_phone: str
    whatsapp_number: str
    default_language: str
    voice_mode: str
    has_twilio_creds: bool
    has_openai_key: bool
    has_elevenlabs_key: bool
    has_smtp: bool


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=SettingsResponse)
async def get_settings(current_user: User = Depends(get_current_user)):
    """Get current user's settings (keys are masked for security)."""
    creds = sqlite_manager.get_credentials_by_user_id(str(current_user.id))

    return SettingsResponse(
        name=current_user.name,
        company_name=current_user.company_name,
        email=current_user.email,
        twilio_phone=current_user.twilio_phone,
        whatsapp_number=current_user.whatsapp_number,
        default_language=current_user.default_language,
        voice_mode=current_user.voice_mode,
        has_twilio_creds=bool(creds and creds.get("twilio_sid")),
        has_openai_key=bool(creds and creds.get("openai_key")),
        has_elevenlabs_key=bool(creds and creds.get("elevenlabs_key")),
        has_smtp=bool(creds and creds.get("smtp_host")),
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(req: SettingsUpdate, current_user: User = Depends(get_current_user)):
    """Save all settings. Syncs credentials to SQLite hot cache immediately."""

    # Update MongoDB profile fields
    if req.name is not None:
        current_user.name = req.name
    if req.company_name is not None:
        current_user.company_name = req.company_name
    if req.default_language is not None:
        current_user.default_language = req.default_language
    if req.voice_mode is not None:
        current_user.voice_mode = req.voice_mode
    if req.twilio_phone is not None:
        current_user.twilio_phone = req.twilio_phone
    if req.whatsapp_number is not None:
        current_user.whatsapp_number = req.whatsapp_number

    current_user.updated_at = datetime.utcnow()
    await current_user.save()

    # Sync sensitive credentials to SQLite hot cache
    if current_user.twilio_phone:
        existing = sqlite_manager.get_credentials_by_user_id(str(current_user.id)) or {}

        sqlite_manager.upsert_credentials({
            "phone_number":          current_user.twilio_phone,
            "user_id":               str(current_user.id),
            "openai_key":            req.openai_key or existing.get("openai_key", ""),
            "elevenlabs_key":        req.elevenlabs_key or existing.get("elevenlabs_key", ""),
            "elevenlabs_voice_id":   req.elevenlabs_voice_id or existing.get("elevenlabs_voice_id", ""),
            "twilio_sid":            req.twilio_sid or existing.get("twilio_sid", ""),
            "twilio_token":          req.twilio_token or existing.get("twilio_token", ""),
            "twilio_phone":          current_user.twilio_phone,
            "elevenlabs_agent_id":   req.elevenlabs_agent_id or existing.get("elevenlabs_agent_id", ""),
            "voice_mode":            current_user.voice_mode,
            "default_language":      current_user.default_language,
            "company_name":          current_user.company_name,
            "whatsapp_number":       current_user.whatsapp_number,
            "smtp_host":             req.smtp_host or existing.get("smtp_host", ""),
            "smtp_port":             req.smtp_port or existing.get("smtp_port", "587"),
            "smtp_user":             req.smtp_user or existing.get("smtp_user", ""),
            "smtp_pass":             req.smtp_pass or existing.get("smtp_pass", ""),
        })
        logger.info("[Settings] Synced credentials to SQLite for %s", current_user.twilio_phone)

    creds = sqlite_manager.get_credentials_by_user_id(str(current_user.id))
    return SettingsResponse(
        name=current_user.name,
        company_name=current_user.company_name,
        email=current_user.email,
        twilio_phone=current_user.twilio_phone,
        whatsapp_number=current_user.whatsapp_number,
        default_language=current_user.default_language,
        voice_mode=current_user.voice_mode,
        has_twilio_creds=bool(creds and creds.get("twilio_sid")),
        has_openai_key=bool(creds and creds.get("openai_key")),
        has_elevenlabs_key=bool(creds and creds.get("elevenlabs_key")),
        has_smtp=bool(creds and creds.get("smtp_host")),
    )


@router.put("/password", status_code=204)
async def change_password(req: PasswordChange, current_user: User = Depends(get_current_user)):
    """Change the current user's password."""
    if not _verify_password(req.current_password, current_user.hashed_password):
        raise HTTPException(400, "Current password is incorrect.")
    current_user.hashed_password = _hash_password(req.new_password)
    current_user.updated_at = datetime.utcnow()
    await current_user.save()
    logger.info("[Settings] Password changed for %s", current_user.email)
