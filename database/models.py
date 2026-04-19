"""
database/models.py — Beanie MongoDB Document models.

Collections:
  - User: Account, hashed password, per-user AI credentials reference.
  - ProductDocument: Uploaded brochures / files for the File Master.
  - CallLog: Full record of every AI telephone call session.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Annotated
from beanie import Document, Indexed
from pydantic import BaseModel, Field, EmailStr


# ─── Sub-models ───────────────────────────────────────────────────────────────

class DocumentTemplate(BaseModel):
    whatsapp_caption: str = ""
    email_subject: str = ""
    email_body: str = ""


class CallAction(BaseModel):
    turn: Optional[int] = None
    action: str
    result: str = "success"
    detail: str = ""


class LanguageDetection(BaseModel):
    language: str = "en"
    confidence: float = 1.0
    source: str = "default"
    turn: int = 0


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Document):
    """
    Main user account.
    Sensitive keys are stored in SQLite for fast telephony access;
    MongoDB holds the rest of the user profile.
    """
    name: str
    email: Annotated[str, Indexed(unique=True)]
    hashed_password: str
    company_name: str = "My Company"

    # Twilio config (replicated in SQLite hot cache)
    twilio_phone: str = ""           # The 'To' number that links inbound calls to this user

    # Settings
    whatsapp_number: str = ""        # Number to send WhatsApp messages from
    default_language: str = "en"
    voice_mode: str = "multilingual"

    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"


# ─── ProductDocument ──────────────────────────────────────────────────────────

class ProductDocument(Document):
    """
    A brochure / file that the AI can send to callers.
    The 'intent_key' is what the AI uses to look up the document (e.g. 'fan', 'wire').
    """
    user_id: str                 # MongoDB User._id (as string)
    intent_key: str              # e.g. 'fan', 'wire', 'lighting'
    name: str                    # Human-readable: 'Fan Brochure 2026'
    url: str                     # Publicly accessible link to the PDF
    templates: DocumentTemplate = Field(default_factory=DocumentTemplate)
    description: str = ""
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "product_documents"


# ─── CallLog ──────────────────────────────────────────────────────────────────

class CallLog(Document):
    """
    Full record of an AI call session — stored after call completion.
    """
    user_id: str
    call_sid: Annotated[str, Indexed()]
    caller_number: str
    called_number: str
    language: str = "en"
    turn_count: int = 0
    message_count: int = 0
    duration_seconds: Optional[float] = None
    actions_taken: List[CallAction] = []
    transcript_summary: str = ""     # Full transcript joined as a string
    status: str = "completed"        # completed | failed | no_response
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None

    class Settings:
        name = "call_logs"
