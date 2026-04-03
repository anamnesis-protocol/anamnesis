"""
api/middleware/auth.py — Subscription gate for Sovereign AI Context

FastAPI dependency that:
 1. Verifies the Supabase JWT from the Authorization header
 2. Checks that the user has an active subscription in the `subscriptions` table
 3. Returns the user_id (UUID string) if valid
 4. Bypasses all checks when SOVEREIGN_ENV=testnet (demo mode, no real billing)

Usage:
 from api.middleware.auth import require_subscription

 @router.post("/provision/start")
 def provision_start(req: ..., user_id: str = Depends(require_subscription)):
 ...
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

    try:
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again.")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    user_id: str = payload.get("sub", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload — missing sub.")

    return user_id


def require_subscription(authorization: str = Header(default="")) -> str:
    """
    Dependency: verify Supabase JWT + active subscription.

    Testnet bypass: When SOVEREIGN_ENV=testnet, skip all checks and return
    'demo-user'. This lets the testnet demo work without Stripe/Supabase.

    Returns: user_id (UUID string) on success.
    Raises: HTTPException 401 (bad token), 402 (no active subscription), 503 (not configured).
    """
    # ── Testnet bypass (Demo Mode) ─────────────────────────────────────────────
    if os.getenv("SOVEREIGN_ENV", "").strip().lower() == "testnet":
        return "demo-user"

    # ── Validate Authorization header ──────────────────────────────────────────
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header required (Bearer <token>). Log in to get a token.",
        )
    token = authorization[7:]

    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    if not jwt_secret:
        raise HTTPException(status_code=503, detail="Auth not configured — SUPABASE_JWT_SECRET missing.")

    try:
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again.")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    user_id: str = payload.get("sub", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload — missing sub.")

    # ── Check subscription in Supabase ─────────────────────────────────────────
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")

    if not supabase_url or not supabase_service_key:
        raise HTTPException(status_code=503, detail="Supabase not configured — SUPABASE_URL/SERVICE_KEY missing.")

    try:
        from supabase import create_client
        sb = create_client(supabase_url, supabase_service_key)
        result = (
            sb.table("subscriptions")
            .select("status")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=402,
            detail="No subscription found — subscribe to provision a vault.",
        )

    if not result.data or result.data.get("status") != "active":
        raise HTTPException(
            status_code=402,
            detail="Active subscription required — subscribe to provision a vault.",
        )

    return user_id
