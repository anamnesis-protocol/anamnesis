"""
api/middleware/auth.py — Auth dependencies for Sovereign AI Context

FastAPI dependencies:
  get_current_user  — verify Supabase JWT, return user_id
                      testnet bypass: returns 'demo-user' when SOVEREIGN_ENV=testnet
"""

import os

import jwt
from fastapi import Header, HTTPException


def get_current_user(authorization: str = Header(default="")) -> str:
    """
    Dependency: verify Supabase JWT only — no subscription check.

    Use this for endpoints that any authenticated user should access
    regardless of subscription status (e.g. managing their own API keys).

    Testnet bypass: returns 'demo-user' when SOVEREIGN_ENV=testnet.

    Returns: user_id (UUID string) on success.
    Raises: HTTPException 401 (bad/missing token), 503 (not configured).
    """
    # ── Testnet bypass ─────────────────────────────────────────────────────────
    if os.getenv("SOVEREIGN_ENV", "").strip().lower() == "testnet":
        return "demo-user"

    # ── Validate JWT ────────────────────────────────────────────────────────────
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header required (Bearer <token>). Log in to get a token.",
        )
    token = authorization[7:]

    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    if not jwt_secret:
        raise HTTPException(status_code=503, detail="Auth not configured — SUPABASE_JWT_SECRET missing.")

    # Decode header without verification to detect the algorithm
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Malformed token header.")

    try:
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=[alg],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again.")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token (alg={alg}): {exc}")

    user_id: str = payload.get("sub", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload — missing sub.")

    return user_id


