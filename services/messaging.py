"""
services/messaging.py — Master Document & Messaging Manager.

This is the central authority for ALL non-voice actions during a call.
The AI only passes an intent (e.g., document_type="fan", method="whatsapp").
This module resolves the exact file URL, formats the message, and dispatches it.

Design principles:
  - AI knows NOTHING about actual URLs or file paths.
  - If you add a new product brochure, update DOCUMENT_CATALOG only.
  - All sends are logged with full detail for audit/tracking.

Currently in MOCK mode (prints to console). To enable real sends:
  - Set WHATSAPP_MODE=real in .env and configure TWILIO_WHATSAPP_NUMBER.
  - Set EMAIL_MODE=real in .env and configure SMTP / SendGrid settings.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state.conversation_state import ConversationState

logger = logging.getLogger(__name__)

# ─── Master Document Catalog ─────────────────────────────────────────────────
#
# THIS IS THE ONLY PLACE TO ADD / UPDATE / REMOVE DOCUMENTS.
# Format: { "intent_key": DocumentEntry }
# The AI passes the intent_key, this catalog resolves everything else.

@dataclass
class DocumentEntry:
    name: str               # Human-readable name for logging & messages
    url: str                # Direct link or hosted URL of the document
    whatsapp_caption: str   # Message body for WhatsApp delivery
    email_subject: str      # Subject line for email delivery
    email_body: str         # Email body text


DOCUMENT_CATALOG: dict[str, DocumentEntry] = {
    "fan": DocumentEntry(
        name="Fan Brochure 2026",
        url="https://yourcompany.com/brochures/fan_brochure_2026.pdf",
        whatsapp_caption=(
            "🌀 *Fan Brochure 2026*\n"
            "Please find our latest Fan product catalog attached.\n"
            "For any queries, contact us anytime!"
        ),
        email_subject="Your Fan Brochure — Company Name",
        email_body=(
            "Dear Customer,\n\n"
            "Thank you for your interest in our Fan products.\n"
            "Please find the full brochure at the link below:\n\n"
            "{url}\n\n"
            "Feel free to reach out if you have any questions.\n\n"
            "Best regards,\nCompany Name Team"
        ),
    ),
    "wire": DocumentEntry(
        name="Wire Brochure 2026",
        url="https://yourcompany.com/brochures/wire_brochure_2026.pdf",
        whatsapp_caption=(
            "🔌 *Wire Products Brochure 2026*\n"
            "Please find our complete Wire product range attached.\n"
            "For any queries, contact us anytime!"
        ),
        email_subject="Your Wire Products Brochure — Company Name",
        email_body=(
            "Dear Customer,\n\n"
            "Thank you for your interest in our Wire products.\n"
            "Please find the full brochure at the link below:\n\n"
            "{url}\n\n"
            "Feel free to reach out if you have any questions.\n\n"
            "Best regards,\nCompany Name Team"
        ),
    ),
}

# Add more products here:
# "lights": DocumentEntry(name="Lights Catalog 2026", url="...", ...),
# "switches": DocumentEntry(name="Switches Brochure", url="...", ...),


# ─── Delivery Modes ──────────────────────────────────────────────────────────

_WHATSAPP_MODE = os.getenv("WHATSAPP_MODE", "mock")   # "mock" | "real"
_EMAIL_MODE = os.getenv("EMAIL_MODE", "mock")          # "mock" | "real"
_TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")


# ─── Public API ──────────────────────────────────────────────────────────────


def resolve_document(document_type: str) -> DocumentEntry | None:
    """
    Look up a document by its intent key.

    Args:
        document_type: Intent key from AI tool call (e.g. "fan", "wire").

    Returns:
        DocumentEntry if found, None if unknown.
    """
    key = document_type.lower().strip()
    entry = DOCUMENT_CATALOG.get(key)
    if entry is None:
        logger.warning("Unknown document_type '%s' — not in catalog.", document_type)
    return entry


def send_whatsapp(
    state: "ConversationState",
    document_type: str,
    phone_number: str | None = None,
) -> dict:
    """
    Send a brochure to a WhatsApp number.

    Uses state.caller_number as the recipient by default.
    Master Manager resolves exactly which document to send.

    Args:
        state:         Current ConversationState (used for caller_number + logging).
        document_type: Brochure key (e.g. "fan", "wire").
        phone_number:  Override recipient number. Defaults to state.caller_number.

    Returns:
        {"success": bool, "message": str}
    """
    recipient = phone_number or state.caller_number
    if not recipient:
        logger.error("[%s] No phone number available to send WhatsApp.", state.call_sid)
        return {"success": False, "message": "No recipient phone number available."}

    doc = resolve_document(document_type)
    if doc is None:
        return {"success": False, "message": f"Unknown brochure type: '{document_type}'"}

    logger.info(
        "[%s] [ACTION] WhatsApp → %s | Document: %s | URL: %s",
        state.call_sid, recipient, doc.name, doc.url,
    )

    if _WHATSAPP_MODE == "real":
        return _send_whatsapp_real(state, recipient, doc)
    else:
        return _send_whatsapp_mock(state, recipient, doc)


def send_email(
    state: "ConversationState",
    document_type: str,
    email_address: str,
) -> dict:
    """
    Send a brochure link to an email address.

    Master Manager resolves exactly which document and template to use.

    Args:
        state:         Current ConversationState (for logging).
        document_type: Brochure key (e.g. "fan", "wire").
        email_address: Recipient email address.

    Returns:
        {"success": bool, "message": str}
    """
    if not email_address:
        return {"success": False, "message": "No email address provided."}

    doc = resolve_document(document_type)
    if doc is None:
        return {"success": False, "message": f"Unknown brochure type: '{document_type}'"}

    logger.info(
        "[%s] [ACTION] Email → %s | Document: %s | URL: %s",
        state.call_sid, email_address, doc.name, doc.url,
    )

    if _EMAIL_MODE == "real":
        return _send_email_real(state, email_address, doc)
    else:
        return _send_email_mock(state, email_address, doc)


def get_available_documents() -> list[str]:
    """Return list of available document intent keys. Used to build AI prompts dynamically."""
    return list(DOCUMENT_CATALOG.keys())


# ─── Mock Implementations (Dev/Test mode) ────────────────────────────────────


def _send_whatsapp_mock(
    state: "ConversationState", recipient: str, doc: DocumentEntry
) -> dict:
    """MOCK: Print what would be sent instead of actually calling Twilio WhatsApp."""
    print("\n" + "=" * 60)
    print("  [MOCK] WHATSAPP MESSAGE QUEUED")
    print(f"  To      : {recipient}")
    print(f"  Document: {doc.name}")
    print(f"  URL     : {doc.url}")
    print(f"  Caption : {doc.whatsapp_caption[:80]}...")
    print("=" * 60 + "\n")
    return {"success": True, "message": f"[MOCK] WhatsApp sent to {recipient} with {doc.name}"}


def _send_email_mock(
    state: "ConversationState", email_address: str, doc: DocumentEntry
) -> dict:
    """MOCK: Print what would be sent instead of actually sending an email."""
    print("\n" + "=" * 60)
    print("  [MOCK] EMAIL QUEUED")
    print(f"  To      : {email_address}")
    print(f"  Subject : {doc.email_subject}")
    print(f"  Document: {doc.name}")
    print(f"  URL     : {doc.url}")
    print("=" * 60 + "\n")
    return {"success": True, "message": f"[MOCK] Email sent to {email_address} with {doc.name}"}


# ─── Real Implementations (Production) ───────────────────────────────────────


def _send_whatsapp_real(
    state: "ConversationState", recipient: str, doc: DocumentEntry
) -> dict:
    """
    Send WhatsApp via Twilio WhatsApp API.

    Requires:
        - TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN in .env
        - TWILIO_WHATSAPP_NUMBER (e.g. whatsapp:+14155238886) in .env
        - Twilio account approved for WhatsApp Business
    """
    try:
        import config
        from twilio.rest import Client

        client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
        wa_to = f"whatsapp:{recipient}" if not recipient.startswith("whatsapp:") else recipient

        message = client.messages.create(
            body=f"{doc.whatsapp_caption}\n\n{doc.url}",
            from_=_TWILIO_WHATSAPP_FROM,
            to=wa_to,
        )
        logger.info("[%s] WhatsApp sent. SID: %s", state.call_sid, message.sid)
        return {"success": True, "message": f"WhatsApp {doc.name} sent to {recipient}. SID: {message.sid}"}

    except Exception as exc:  # noqa: BLE001
        logger.error("[%s] WhatsApp send failed: %s", state.call_sid, exc)
        return {"success": False, "message": f"WhatsApp failed: {exc}"}


def _send_email_real(
    state: "ConversationState", email_address: str, doc: DocumentEntry
) -> dict:
    """
    Send email via SMTP / SendGrid.

    Requires:
        - SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD in .env
        - Or SENDGRID_API_KEY in .env for SendGrid
    """
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_host = os.environ["SMTP_HOST"]
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.environ["SMTP_USER"]
        smtp_pass = os.environ["SMTP_PASSWORD"]
        from_email = os.getenv("SMTP_FROM_EMAIL", smtp_user)

        body_text = doc.email_body.format(url=doc.url)

        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = email_address
        msg["Subject"] = doc.email_subject
        msg.attach(MIMEText(body_text, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, email_address, msg.as_string())

        logger.info("[%s] Email sent to %s.", state.call_sid, email_address)
        return {"success": True, "message": f"Email sent to {email_address} with {doc.name}"}

    except Exception as exc:  # noqa: BLE001
        logger.error("[%s] Email send failed: %s", state.call_sid, exc)
        return {"success": False, "message": f"Email failed: {exc}"}
