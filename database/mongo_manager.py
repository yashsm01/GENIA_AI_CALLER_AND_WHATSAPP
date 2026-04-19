"""
database/mongo_manager.py — MongoDB connection via Motor + Beanie.

Call `init_mongo()` once on app startup.
"""

from __future__ import annotations

import logging
import os
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from database.models import User, ProductDocument, CallLog

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None


async def init_mongo() -> None:
    """Initialize the MongoDB connection and Beanie ODM."""
    global _client
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB", "ai_auto_caller")

    _client = AsyncIOMotorClient(uri)
    db = _client[db_name]

    await init_beanie(
        database=db,
        document_models=[User, ProductDocument, CallLog],
    )
    logger.info("[MongoDB] Connected to %s / %s", uri.split("@")[-1], db_name)


async def close_mongo() -> None:
    """Close the MongoDB connection gracefully."""
    global _client
    if _client:
        _client.close()
        _client = None
        logger.info("[MongoDB] Connection closed.")
