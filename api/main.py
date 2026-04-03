"""
api/main.py — Sovereign AI Context SaaS API

FastAPI application for multi-user sovereign AI session management.

Usage:
 cd D:/code/sovereign-ai-context
 uvicorn api.main:app --reload --port 8000

Endpoints:
 POST /session/challenge — Get challenge for wallet to sign
 POST /session/open — Open session (wallet sig → key → decrypt HFS → context)
 POST /session/close — Close session (log SESSION_ENDED to HCS)
 GET /session/status — Active session count / health
 GET /docs — Interactive API docs (Swagger UI)

Requirements:
 .env must contain: OPERATOR_ID, OPERATOR_KEY, CONTEXT_TOKEN_ID (as fallback), VALIDATOR_CONTRACT_ID
"""

import sys
from pathlib import Path

# Ensure project root is on path regardless of CWD
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from dotenv import load_dotenv

# SOVEREIGN_ENV=testnet → load .env.testnet (for demo/staging)
# Default: .env (mainnet / production)
_env_name = os.getenv("SOVEREIGN_ENV", "").strip().lower()
_env_file = ".env.testnet" if _env_name == "testnet" else ".env"
load_dotenv(_env_file, override=True)
print(f"[api] Network: {os.getenv('HEDERA_NETWORK', 'unset')} (SOVEREIGN_ENV={_env_name or 'unset'}, loaded {_env_file})")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.limiter import limiter
from api.routes.session import router as session_router
from api.routes.user import router as user_router
from api.routes.demo import router as demo_router
from api.routes.auth import router as auth_router
from api.routes.billing import router as billing_router
from api.routes.chat import router as chat_router
from api.routes.user_keys import router as user_keys_router
from api.routes.vault import router as vault_router
from api.routes.skills import router as skills_router

app = FastAPI(
 title="Sovereign AI Context API",
 description=(
 "Multi-user SaaS API for token-gated AI context management. "
 "Each user's AI context is encrypted on Hedera File Service, "
 "gated by their context token (NFT), and accessed via wallet signature. "
 "Proof-of-concept implementation of sovereign AI context ownership."
 ),
 version="0.1.0",
)

# ── Rate limiting ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — locked to the production domain; localhost allowed for local dev
_FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8001").rstrip("/")
_CORS_ORIGINS = [_FRONTEND_URL]
if "localhost" not in _FRONTEND_URL:
 _CORS_ORIGINS += ["http://localhost:8000", "http://localhost:8001"]

app.add_middleware(
 CORSMiddleware,
 allow_origins=_CORS_ORIGINS,
 allow_methods=["POST", "GET", "DELETE"],
 allow_headers=["*"],
)

app.include_router(session_router)
app.include_router(user_router)
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(chat_router)
app.include_router(user_keys_router)
app.include_router(vault_router)
app.include_router(skills_router)

# Demo router (server-side signing, no wallet) — testnet/dev only
if _env_name == "testnet":
 app.include_router(demo_router)


@app.get("/health")
def health():
 return {"status": "ok"}


# Serve frontend at root — MUST be last: StaticFiles mount is greedy.
# All API routes and @app.get() handlers registered above take priority.
# SPA: index.html served for any path not matched by an API route.
_FRONTEND = Path(__file__).parent.parent / "frontend"
if _FRONTEND.exists():
 app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")
