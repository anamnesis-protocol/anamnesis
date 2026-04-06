"""
api/middleware/auth.py — Auth dependencies for Sovereign AI Context

FastAPI dependencies:
  get_current_user  — verify Supabase JWT, return user_id
                      testnet bypass: returns 'demo-user' when SOVEREIGN_ENV=testnet

Supabase issues RS256 JWTs (asymmetric). Verification uses the JWKS endpoint:
  {SUPABASE_URL}/auth/v1/.well-known/jwks.json

SUPABASE_JWT_SECRET is kept for fallback HS256 compatibility only.
"""

import os

import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException

_SYMMETRIC_ALGS = {"HS256", "HS384", "HS512"}

# Module-level JWKS client — caches keys, avoids refetching on every request
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supabase_url:
            raise RuntimeError("SUPABASE_URL not configured.")
        _jwks_client = PyJWKClient(f"{supabase_url}/auth/v1/.well-known/jwks.json")
    return _jwks_client


def get_current_user(authorization: str = Header(default="")) -> str:
    """
    Dependency: verify Supabase JWT only — no subscription check.

    Supports both RS256 (Supabase default) and HS256 (legacy/testnet).
    Testnet bypass: returns 'demo-user' when SOVEREIGN_ENV=testnet.

    Returns: user_id (UUID string) on success.
    Raises: HTTPException 401 (bad/missing token), 503 (not configured).
    """
    # ── Testnet bypass ─────────────────────────────────────────────────────────
    if os.getenv("SOVEREIGN_ENV", "").strip().lower() == "testnet":
        return "demo-user"

    # ── Extract token ───────────────────────────────────────────────────────────
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header required (Bearer <token>). Log in to get a token.",
        )
    token = authorization[7:]

    # ── Detect algorithm ────────────────────────────────────────────────────────
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "RS256")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Malformed token header.")

    # ── Verify ──────────────────────────────────────────────────────────────────
    try:
        if alg in _SYMMETRIC_ALGS:
            # HS256 fallback — use the JWT secret
            jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
            if not jwt_secret:
                raise HTTPException(status_code=503, detail="Auth not configured — SUPABASE_JWT_SECRET missing.")
            payload = jwt.decode(token, jwt_secret, algorithms=[alg], audience="authenticated")
        else:
            # RS256 (and other asymmetric) — use JWKS endpoint
            try:
                jwks_client = _get_jwks_client()
                signing_key = jwks_client.get_signing_key_from_jwt(token)
            except Exception as exc:
                raise HTTPException(status_code=503, detail=f"Failed to fetch signing key: {exc}")
            payload = jwt.decode(token, signing_key.key, algorithms=[alg], audience="authenticated")
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again.")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    user_id: str = payload.get("sub", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload — missing sub.")

    return user_id


