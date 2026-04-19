"""
database/sqlite_manager.py — Fast SQLite Hot Cache for Credential Lookups.

Stores per-user Twilio/AI keys in a local SQLite file.
This is accessed at call start time (must be millisecond-fast).

Schema: credentials table
 - phone_number (PK): The Twilio 'To' number for this user
 - user_id: MongoDB ObjectId reference
 - openai_key, elevenlabs_key, elevenlabs_voice_id
 - twilio_sid, twilio_token, twilio_phone
 - elevenlabs_agent_id, voice_mode, default_language
"""

from __future__ import annotations

import sqlite3
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "data" / "credentials.db"


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db() -> None:
    """Create the credentials table if it doesn't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                phone_number    TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL,
                openai_key      TEXT NOT NULL,
                elevenlabs_key  TEXT NOT NULL,
                elevenlabs_voice_id TEXT NOT NULL,
                twilio_sid      TEXT NOT NULL,
                twilio_token    TEXT NOT NULL,
                twilio_phone    TEXT NOT NULL,
                elevenlabs_agent_id TEXT DEFAULT '',
                voice_mode      TEXT DEFAULT 'multilingual',
                default_language TEXT DEFAULT 'en',
                company_name    TEXT DEFAULT 'Company',
                whatsapp_number TEXT DEFAULT '',
                smtp_host       TEXT DEFAULT '',
                smtp_port       TEXT DEFAULT '587',
                smtp_user       TEXT DEFAULT '',
                smtp_pass       TEXT DEFAULT '',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    logger.info("[SQLite] Credentials DB initialized at %s", _DB_PATH)


def upsert_credentials(creds: dict) -> None:
    """Insert or replace credentials for a phone number (called when user saves settings)."""
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO credentials (
                phone_number, user_id, openai_key, elevenlabs_key, elevenlabs_voice_id,
                twilio_sid, twilio_token, twilio_phone, elevenlabs_agent_id,
                voice_mode, default_language, company_name, whatsapp_number,
                smtp_host, smtp_port, smtp_user, smtp_pass, updated_at
            ) VALUES (
                :phone_number, :user_id, :openai_key, :elevenlabs_key, :elevenlabs_voice_id,
                :twilio_sid, :twilio_token, :twilio_phone, :elevenlabs_agent_id,
                :voice_mode, :default_language, :company_name, :whatsapp_number,
                :smtp_host, :smtp_port, :smtp_user, :smtp_pass, CURRENT_TIMESTAMP
            )
            ON CONFLICT(phone_number) DO UPDATE SET
                openai_key          = excluded.openai_key,
                elevenlabs_key      = excluded.elevenlabs_key,
                elevenlabs_voice_id = excluded.elevenlabs_voice_id,
                twilio_sid          = excluded.twilio_sid,
                twilio_token        = excluded.twilio_token,
                elevenlabs_agent_id = excluded.elevenlabs_agent_id,
                voice_mode          = excluded.voice_mode,
                default_language    = excluded.default_language,
                company_name        = excluded.company_name,
                whatsapp_number     = excluded.whatsapp_number,
                smtp_host           = excluded.smtp_host,
                smtp_port           = excluded.smtp_port,
                smtp_user           = excluded.smtp_user,
                smtp_pass           = excluded.smtp_pass,
                updated_at          = CURRENT_TIMESTAMP
        """, creds)
        conn.commit()
    logger.info("[SQLite] Credentials upserted for %s", creds.get("phone_number"))


def get_credentials_by_phone(phone_number: str) -> Optional[dict]:
    """
    Fetch credentials for a given Twilio phone number.
    Called at call start — MUST be fast.
    Returns dict or None if not found.
    """
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM credentials WHERE phone_number = ?", (phone_number,)
        ).fetchone()
    if row is None:
        logger.warning("[SQLite] No credentials found for phone: %s", phone_number)
        return None
    return dict(row)


def get_credentials_by_user_id(user_id: str) -> Optional[dict]:
    """Fetch credentials by MongoDB user_id."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM credentials WHERE user_id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def delete_credentials(phone_number: str) -> None:
    """Remove credentials (called when user deletes their account)."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM credentials WHERE phone_number = ?", (phone_number,))
        conn.commit()
