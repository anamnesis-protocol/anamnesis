"""
api/routes/demo.py — Demo-only endpoints for the demo.

IMPORTANT: Disable this router before production deployment.
These endpoints exist solely to make the live demo work without requiring
a real HashPack wallet. The operator key signs challenges on behalf of the demo user.

/demo/sign — Signs a session challenge with the operator Ed25519 key
/demo/status — Returns demo mode status and environment info (no secrets)
"""

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.crypto import make_challenge
from src.config import get_treasury

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoSignRequest(BaseModel):
    token_id: str


class DemoSignResponse(BaseModel):
    token_id: str
    challenge_hex: str
    signature_hex: str
    note: str = "Signed with operator demo key — replace with user wallet in production."


@router.post("/sign", response_model=DemoSignResponse)
def demo_sign(req: DemoSignRequest) -> DemoSignResponse:
    """
    Sign a session challenge with the operator Ed25519 key.

    Demo-only. Allows the frontend to demonstrate the full provision → session
    lifecycle without requiring a real user wallet.

    In production: the user's wallet (HashPack) signs this challenge client-side.
    The signature never leaves the user's device — only its effect on decryption proves ownership.
    """
    try:
        _, treasury_key = get_treasury()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Operator key not configured: {exc}")

    challenge = make_challenge(req.token_id)
    try:
        signature: bytes = treasury_key.sign(challenge)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Signing failed: {exc}")

    return DemoSignResponse(
        token_id=req.token_id,
        challenge_hex=challenge.hex(),
        signature_hex=signature.hex(),
    )


@router.get("/status")
def demo_status():
    """Return demo mode info. No secrets exposed."""
    return {
        "demo_mode": True,
        "warning": "Demo endpoints active — disable DEMO_ROUTER before production deployment.",
        "endpoints": {
            "sign": "POST /demo/sign — signs challenge with operator key (no wallet required)",
        },
    }
