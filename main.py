"""
main.py — AI Auto Caller entry point.

Starts the FastAPI/uvicorn server, initializes databases, mounts API routers,
and serves the React frontend from the /app path.
"""

import logging
import sys
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

import config
from telephony.call_handler import app
from database import sqlite_manager
from database.mongo_manager import init_mongo, close_mongo

# ─── Logging Setup ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ─── Lifespan (startup / shutdown) ───────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):
    # Startup
    logger.info("[Startup] Initializing SQLite hot cache...")
    sqlite_manager.initialize_db()

    logger.info("[Startup] Connecting to MongoDB...")
    try:
        await init_mongo()
    except Exception as exc:
        logger.error("[Startup] MongoDB connection failed: %s", exc)
        import traceback
        traceback.print_exc()

    yield
    await close_mongo()
    logger.info("[Shutdown] MongoDB connection closed.")

app.router.lifespan_context = lifespan

# ─── Static Files & SPA Fallback ──────────────────────────────────────────────
# We mount this BEFORE routers to ensure assets take precedence if there's any conflict

_FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"

if _FRONTEND_DIST.exists():
    # Mount the dist folder. html=True handles /app -> /app/index.html
    app.mount("/app", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
    logger.info("[Frontend] React dashboard mounted at /app")
else:
    logger.warning("[Frontend] No dist build found at %s", _FRONTEND_DIST)

# ─── Mount API Routers ────────────────────────────────────────────────────────

from api.auth import router as auth_router
from api.documents import router as documents_router
from api.calls import router as calls_router
from api.settings import router as settings_router

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(calls_router)
app.include_router(settings_router)

# ─── SPA Fallback ─────────────────────────────────────────────────────────────

@app.exception_handler(404)
async def spa_fallback(request, exc):
    # If the request starts with /app but wasn't found by StaticFiles, it's a React route
    if request.url.path.startswith("/app"):
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
    return JSONResponse({"detail": "Not Found"}, status_code=404)

# ─── Startup Banner ───────────────────────────────────────────────────────────

def _print_banner() -> None:
    def mask(v: str) -> str:
        return (v[:4] + "****" + v[-4:]) if v and len(v) > 8 else "****"

    print("\n" + "=" * 60)
    print("  AI AUTO CALLER — Multi-tenant SaaS")
    print("=" * 60)
    print(f"  Dashboard     : {config.PUBLIC_BASE_URL}/app")
    print(f"  MongoDB       : {os.getenv('MONGODB_URI', 'mongodb://localhost:27017')[:30]}...")
    print(f"  Twilio Phone  : {config.TWILIO_PHONE_NUMBER}")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    _print_banner()
    uvicorn.run(
        "telephony.call_handler:app",
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        reload=False,
        log_level="info",
    )
