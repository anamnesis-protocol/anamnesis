"""
api/routes/user_keys.py — Per-user AI model API key management.

Endpoints:
 GET /user/keys → list which providers have a key configured
 POST /user/keys/{provider} → save (or update) an encrypted API key
 DELETE /user/keys/{provider} → remove a stored key

Auth:
 All endpoints require a valid Supabase JWT (Bearer token).
 Uses get_current_user() — JWT verification only, no subscription check.
 This lets users configure their keys before or after subscribing.

Security:
 Keys are Fernet-encrypted at the app layer before Supabase write.
 GET /user/keys returns ONLY the list of configured provider names
 — never the actual key values.
 Demo mode (SOVEREIGN_ENV=testnet) returns {"configured": [], "demo": true}
 and rejects save/delete requests.
"""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.middleware.auth import get_current_user
from api.services.ai_router import MODELS
from api.services.key_store import (
    delete_user_key,
    get_key_status,
    save_user_key,
)

router = APIRouter(prefix="/user/keys", tags=["keys"])

# Derived from the live model registry — stays in sync automatically as providers are added.
_VALID_PROVIDERS: set[str] = {meta["provider"] for meta in MODELS.values()}


class KeyRequest(BaseModel):
    key: str


# ---------------------------------------------------------------------------
# GET /user/keys
# ---------------------------------------------------------------------------

@router.get("")
def list_configured(user_id: str = Depends(get_current_user)):
    """
    Return which AI providers have a key configured for this user.

    Response fields:
    configured — providers with a readable, decryptable key.
    corrupted_providers — providers where the stored key cannot be decrypted
    (written with a different secret, or data corruption).
    Frontend should prompt the user to re-enter these keys.

    Never returns actual key values.
    """
    if user_id == "demo-user":
        return {
            "configured": [],
            "corrupted_providers": [],
            "demo": True,
            "message": "Demo mode — keys are sourced from server environment. Log in to manage your own keys.",
        }
    configured, corrupted = get_key_status(user_id)
    return {"configured": configured, "corrupted_providers": corrupted}


# ---------------------------------------------------------------------------
# POST /user/keys/{provider}
# ---------------------------------------------------------------------------

@router.post("/{provider}")
def save_key(
    provider: str,
    req: KeyRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Encrypt and store an API key for the given provider.
    Upserts — if a key for this provider already exists, it is replaced.
    """
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'. Valid: openai, anthropic, google, mistral, groq, ollama.")
    if user_id == "demo-user":
        raise HTTPException(status_code=400, detail="Cannot save keys in demo mode. Create a real account to manage your own keys.")
    if not req.key.strip():
        raise HTTPException(status_code=400, detail="API key cannot be empty.")

    try:
        save_user_key(user_id, provider, req.key.strip())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return {"saved": provider}


# ---------------------------------------------------------------------------
# DELETE /user/keys/{provider}
# ---------------------------------------------------------------------------

@router.delete("/{provider}")
def remove_key(
    provider: str,
    user_id: str = Depends(get_current_user),
):
    """Remove the stored API key for a provider."""
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'.")
    if user_id == "demo-user":
        raise HTTPException(status_code=400, detail="No keys to delete in demo mode.")

    try:
        delete_user_key(user_id, provider)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return {"deleted": provider}
