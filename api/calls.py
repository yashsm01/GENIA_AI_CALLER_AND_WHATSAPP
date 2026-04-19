"""
api/calls.py — Call History endpoints.

Routes:
  GET  /api/calls       - List recent calls for the current user
  GET  /api/calls/{id}  - Full detail for a specific call
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database.models import CallLog, User
from api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/calls", tags=["calls"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CallSummary(BaseModel):
    id: str
    call_sid: str
    caller_number: str
    language: str
    turn_count: int
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    actions_count: int


class CallDetail(BaseModel):
    id: str
    call_sid: str
    caller_number: str
    called_number: str
    language: str
    turn_count: int
    message_count: int
    duration_seconds: Optional[float]
    actions_taken: list
    transcript_summary: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime]


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[CallSummary])
async def list_calls(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """Return recent call logs for the current user."""
    logs = await CallLog.find(
        CallLog.user_id == str(current_user.id)
    ).sort("-started_at").limit(limit).to_list()

    return [
        CallSummary(
            id=str(c.id),
            call_sid=c.call_sid,
            caller_number=c.caller_number,
            language=c.language,
            turn_count=c.turn_count,
            status=c.status,
            started_at=c.started_at,
            ended_at=c.ended_at,
            actions_count=len(c.actions_taken),
        )
        for c in logs
    ]


@router.get("/{log_id}", response_model=CallDetail)
async def get_call(log_id: str, current_user: User = Depends(get_current_user)):
    """Get full call detail including transcript and actions."""
    log = await CallLog.get(log_id)
    if not log or log.user_id != str(current_user.id):
        from fastapi import HTTPException
        raise HTTPException(404, "Call log not found.")

    return CallDetail(
        id=str(log.id),
        call_sid=log.call_sid,
        caller_number=log.caller_number,
        called_number=log.called_number,
        language=log.language,
        turn_count=log.turn_count,
        message_count=log.message_count,
        duration_seconds=log.duration_seconds,
        actions_taken=[a.model_dump() for a in log.actions_taken],
        transcript_summary=log.transcript_summary,
        status=log.status,
        started_at=log.started_at,
        ended_at=log.ended_at,
    )
