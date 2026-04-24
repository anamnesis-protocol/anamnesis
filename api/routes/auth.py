"""
api/routes/auth.py — Auth endpoints (thin Supabase proxy)

Keeps the frontend talking to our backend domain only — no direct Supabase calls
from the browser. This lets us control rate limits, add audit logging, and swap
auth providers without touching the frontend.

Endpoints:
 POST /auth/signup — Create account → return access_token
 POST /auth/login — Sign in → return access_token
 GET /auth/status — Verify token + return subscription status

Note: We use the Service Role key for signup (to create subscription row),
 and the Anon key for login (user-scoped operations).
"""

import os

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from api.limiter import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request models ─────────────────────────────────────────────────────────────


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


# ── Helpers ────────────────────────────────────────────────────────────────────


def _supabase_service():
    """Return Supabase client with service role key (admin access)."""
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not supabase_url or not service_key:
        raise HTTPException(503, "Auth service not configured — SUPABASE_URL/SERVICE_KEY missing.")
    from supabase import create_client

    return create_client(supabase_url, service_key)


def _supabase_anon():
    """Return Supabase client with anon key (user-scoped access)."""
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        raise HTTPException(503, "Auth service not configured — SUPABASE_URL/ANON_KEY missing.")
    from supabase import create_client

    return create_client(supabase_url, anon_key)


# ── POST /auth/signup ──────────────────────────────────────────────────────────


@router.post("/signup")
@limiter.limit("3/minute")
def signup(request: Request, req: SignupRequest):
    """
    Create a new user account via Supabase Auth.

    Creates the user and an inactive subscription row. Returns an access_token
    if email confirmation is disabled in Supabase; otherwise returns a message
    telling the user to confirm their email before logging in.
    """
    sb = _supabase_service()

    try:
        res = sb.auth.sign_up({"email": req.email, "password": req.password})
    except Exception as exc:
        raise HTTPException(400, str(exc))

    if res.user is None:
        raise HTTPException(400, "Signup failed — check your email and password.")

    user_id = str(res.user.id)

    # Create an inactive subscription row for this user
    try:
        sb.table("subscriptions").insert(
            {
                "user_id": user_id,
                "status": "inactive",
            }
        ).execute()
    except Exception:
        pass  # Row may already exist from a previous partial signup

    if res.session:
        # Email confirmation disabled — user is logged in immediately
        return {
            "user_id": user_id,
            "email": res.user.email,
            "access_token": res.session.access_token,
            "confirm_email": False,
        }
    else:
        # Email confirmation required — prompt user to check inbox
        return {
            "user_id": user_id,
            "email": res.user.email,
            "access_token": None,
            "confirm_email": True,
            "message": "Check your email to confirm your account, then log in.",
        }


# ── POST /auth/login ───────────────────────────────────────────────────────────


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, req: LoginRequest):
    """
    Sign in with email + password.

    Returns access_token for use in Authorization: Bearer headers.
    """
    sb = _supabase_anon()

    try:
        res = sb.auth.sign_in_with_password({"email": req.email, "password": req.password})
    except Exception:
        raise HTTPException(401, "Invalid email or password.")

    if not res.session:
        raise HTTPException(401, "Login failed — please check your credentials.")

    return {
        "user_id": str(res.user.id),
        "email": res.user.email,
        "access_token": res.session.access_token,
    }


# ── GET /auth/status ───────────────────────────────────────────────────────────


@router.get("/status")
@limiter.limit("30/minute")
def auth_status(request: Request, authorization: str = Header(default="")):
    """
    Verify the JWT and return the user's subscription status.
    Used by the frontend on page load to restore auth state.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authorization header required.")

    import jwt

    token = authorization[7:]
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    if not jwt_secret:
        raise HTTPException(503, "Auth not configured.")

    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"], audience="authenticated")
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired.")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token.")

    user_id = payload.get("sub", "")
    email = payload.get("email", "")

    sb = _supabase_service()
    try:
        result = (
            sb.table("subscriptions")
            .select("status, current_period_end")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        sub_data = result.data or {}
    except Exception:
        sub_data = {}

    return {
        "user_id": user_id,
        "email": email,
        "subscription_status": sub_data.get("status", "inactive"),
        "current_period_end": sub_data.get("current_period_end"),
    }
