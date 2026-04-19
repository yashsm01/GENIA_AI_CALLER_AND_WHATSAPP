"""
api/documents.py — File Master CRUD endpoints.

Routes:
  GET    /api/documents        - List all documents for current user
  POST   /api/documents        - Upload / create a new document
  PUT    /api/documents/{id}   - Update document details
  DELETE /api/documents/{id}   - Remove a document
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database.models import ProductDocument, DocumentTemplate, User
from api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class DocumentCreate(BaseModel):
    intent_key: str
    name: str
    url: str
    description: str = ""
    whatsapp_caption: str = ""
    email_subject: str = ""
    email_body: str = ""


class DocumentUpdate(BaseModel):
    intent_key: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    whatsapp_caption: Optional[str] = None
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    is_active: Optional[bool] = None


class DocumentResponse(BaseModel):
    id: str
    intent_key: str
    name: str
    url: str
    description: str
    whatsapp_caption: str
    email_subject: str
    email_body: str
    is_active: bool
    created_at: datetime


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[DocumentResponse])
async def list_documents(current_user: User = Depends(get_current_user)):
    """List all documents for the logged-in user."""
    docs = await ProductDocument.find(
        ProductDocument.user_id == str(current_user.id)
    ).sort("+created_at").to_list()

    return [
        DocumentResponse(
            id=str(d.id),
            intent_key=d.intent_key,
            name=d.name,
            url=d.url,
            description=d.description,
            whatsapp_caption=d.templates.whatsapp_caption,
            email_subject=d.templates.email_subject,
            email_body=d.templates.email_body,
            is_active=d.is_active,
            created_at=d.created_at,
        )
        for d in docs
    ]


@router.post("", response_model=DocumentResponse, status_code=201)
async def create_document(req: DocumentCreate, current_user: User = Depends(get_current_user)):
    """Create a new document entry in the File Master."""
    # Check for duplicate intent_key per user
    existing = await ProductDocument.find_one(
        ProductDocument.user_id == str(current_user.id),
        ProductDocument.intent_key == req.intent_key.lower().strip(),
    )
    if existing:
        raise HTTPException(400, f"Intent key '{req.intent_key}' already exists.")

    doc = ProductDocument(
        user_id=str(current_user.id),
        intent_key=req.intent_key.lower().strip(),
        name=req.name,
        url=req.url,
        description=req.description,
        templates=DocumentTemplate(
            whatsapp_caption=req.whatsapp_caption,
            email_subject=req.email_subject,
            email_body=req.email_body,
        ),
    )
    await doc.insert()
    logger.info("[Docs] Created document '%s' for user %s", req.name, current_user.email)

    return DocumentResponse(
        id=str(doc.id),
        intent_key=doc.intent_key,
        name=doc.name,
        url=doc.url,
        description=doc.description,
        whatsapp_caption=doc.templates.whatsapp_caption,
        email_subject=doc.templates.email_subject,
        email_body=doc.templates.email_body,
        is_active=doc.is_active,
        created_at=doc.created_at,
    )


@router.put("/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: str,
    req: DocumentUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update a document entry."""
    doc = await ProductDocument.get(doc_id)
    if not doc or doc.user_id != str(current_user.id):
        raise HTTPException(404, "Document not found.")

    if req.intent_key is not None:
        doc.intent_key = req.intent_key.lower().strip()
    if req.name is not None:
        doc.name = req.name
    if req.url is not None:
        doc.url = req.url
    if req.description is not None:
        doc.description = req.description
    if req.is_active is not None:
        doc.is_active = req.is_active
    if req.whatsapp_caption is not None:
        doc.templates.whatsapp_caption = req.whatsapp_caption
    if req.email_subject is not None:
        doc.templates.email_subject = req.email_subject
    if req.email_body is not None:
        doc.templates.email_body = req.email_body

    await doc.save()
    logger.info("[Docs] Updated document '%s'", doc.name)

    return DocumentResponse(
        id=str(doc.id),
        intent_key=doc.intent_key,
        name=doc.name,
        url=doc.url,
        description=doc.description,
        whatsapp_caption=doc.templates.whatsapp_caption,
        email_subject=doc.templates.email_subject,
        email_body=doc.templates.email_body,
        is_active=doc.is_active,
        created_at=doc.created_at,
    )


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, current_user: User = Depends(get_current_user)):
    """Delete a document from the File Master."""
    doc = await ProductDocument.get(doc_id)
    if not doc or doc.user_id != str(current_user.id):
        raise HTTPException(404, "Document not found.")
    await doc.delete()
    logger.info("[Docs] Deleted document '%s'", doc.name)
