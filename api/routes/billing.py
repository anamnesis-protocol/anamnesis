"""
api/routes/billing.py — Arty Fitchels subscription billing (Stripe / USD only)

Pricing:
 $99 one-time setup fee — mints the vault on Hedera, yours forever
 $40 /month recurring — keeps your AI context active and accessible

Payment path:
 Stripe hosted Checkout Session with two line items:
 1. $99 one-time setup fee (first invoice only)
 2. $40/month recurring subscription
 → webhook confirms payment → subscription marked active in Supabase

Environment variables required:
 STRIPE_SECRET_KEY — Stripe secret key (sk_live_...)
 STRIPE_PUBLISHABLE_KEY — Stripe publishable key (pk_live_...)
 STRIPE_WEBHOOK_SECRET — Stripe webhook signing secret (whsec_...)
 STRIPE_SETUP_PRICE_ID — Price ID for the $99 one-time setup product
 STRIPE_MONTHLY_PRICE_ID — Price ID for the $40/month recurring product

Supabase `subscriptions` table schema (run in Supabase SQL editor):
 create table subscriptions (
 id uuid primary key default gen_random_uuid(),
 user_id uuid references auth.users(id) not null,
 stripe_customer_id text,
 stripe_subscription_id text,
 status text not null default 'inactive',
 plan text not null default 'monthly',
 current_period_end timestamptz,
 created_at timestamptz default now(),
 updated_at timestamptz default now()
 );
 alter table subscriptions enable row level security;
 create policy "Users read own" on subscriptions
 for select using (auth.uid() = user_id);

Endpoints:
 POST /billing/create-checkout — Stripe Checkout Session (setup fee + subscription)
 POST /billing/webhook — Stripe webhook handler (no auth, sig verified)
 GET /billing/status — Return current subscription status for user
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from api.limiter import limiter
from api.middleware.auth import get_current_user

router = APIRouter(prefix="/billing", tags=["billing"])


# ── Internal helpers ───────────────────────────────────────────────────────────

def _supabase_service():
 url = os.getenv("SUPABASE_URL")
 key = os.getenv("SUPABASE_SERVICE_KEY")
 if not url or not key:
 raise HTTPException(503, "Supabase not configured.")
 from supabase import create_client
 return create_client(url, key)


# ── POST /billing/create-checkout ─────────────────────────────────────────────

@router.post("/create-checkout")
@limiter.limit("3/minute")
def create_checkout(request: Request, user_id: str = Depends(get_current_user)):
 """
 Create a Stripe Checkout Session for Arty Fitchels onboarding.

 Charges in a single session (mode=subscription):
 $99 one-time setup fee — billed on the first invoice alongside month 1
 $40/month recurring — continues automatically each month

 Stripe adds the setup fee as a one-time line item to the subscription's
 first invoice. Subsequent invoices contain only the $40/month charge.

 Requires env vars:
 STRIPE_SETUP_PRICE_ID — Price ID for the $99 one-time product
 STRIPE_MONTHLY_PRICE_ID — Price ID for the $40/month recurring product

 Returns { checkout_url } — redirect the browser here to complete payment.
 After success, Stripe redirects to /?payment=success.
 After cancel, Stripe redirects to /?payment=cancelled.
 """
 if user_id == "demo-user":
 raise HTTPException(400, "Cannot create a checkout session in demo mode.")
 stripe = _get_stripe()
 setup_price_id = os.getenv("STRIPE_SETUP_PRICE_ID")
 monthly_price_id = os.getenv("STRIPE_MONTHLY_PRICE_ID")

 if not setup_price_id:
 raise HTTPException(503, "STRIPE_SETUP_PRICE_ID not configured.")
 if not monthly_price_id:
 raise HTTPException(503, "STRIPE_MONTHLY_PRICE_ID not configured.")

 sb = _supabase_service()

 # ── Get or create Stripe customer ──────────────────────────────────────────
 try:
 result = (
 sb.table("subscriptions")
 .select("stripe_customer_id")
 .eq("user_id", user_id)
 .single()
 .execute()
 )
 customer_id = (result.data or {}).get("stripe_customer_id")
 except Exception:
 customer_id = None

 if not customer_id:
 customer = stripe.Customer.create(metadata={"user_id": user_id})
 customer_id = customer.id
 sb.table("subscriptions").upsert({
 "user_id": user_id,
 "stripe_customer_id": customer_id,
 "status": "inactive",
 }).execute()

 # ── Create Checkout Session (setup fee + subscription) ────────────────────
 # Stripe supports one-time line items alongside recurring items in
 # mode="subscription". The setup fee appears on the first invoice only.
 base_url = os.getenv("FRONTEND_URL", "http://localhost:8001").rstrip("/")
 session = stripe.checkout.Session.create(
 customer=customer_id,
 mode="subscription",
 line_items=[
 {"price": setup_price_id, "quantity": 1}, # $99 one-time
 {"price": monthly_price_id, "quantity": 1}, # $40/month
 ],
 success_url=f"{base_url}/?payment=success",
 cancel_url=f"{base_url}/?payment=cancelled",
 metadata={"user_id": user_id},
 )

 return {"checkout_url": session.url}


# ── POST /billing/webhook ──────────────────────────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(request: Request):
 """
 Stripe webhook handler. Verifies the Stripe-Signature header.

 Handled events:
 invoice.payment_succeeded → mark subscription active
 customer.subscription.updated → sync status (pause/resume)
 customer.subscription.deleted → mark inactive (cancelled)
 """
 payload = await request.body()
 sig_header = request.headers.get("stripe-signature", "")
 webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
 stripe = _get_stripe()

 try:
 event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
 except stripe.error.SignatureVerificationError:
 raise HTTPException(400, "Invalid Stripe webhook signature.")
 except Exception as exc:
 raise HTTPException(400, f"Webhook error: {exc}")

 sb = _supabase_service()

 if event["type"] == "invoice.payment_succeeded":
 invoice = event["data"]["object"]
 customer_id = invoice.get("customer")
 stripe_sub_id = invoice.get("subscription")

 if stripe_sub_id:
 # Idempotency guard: skip if already active for this subscription.
 # Stripe retries webhooks on failure — this prevents duplicate writes.
 try:
 existing = (
 sb.table("subscriptions")
 .select("status, stripe_subscription_id")
 .eq("stripe_customer_id", customer_id)
 .single()
 .execute()
 )
 row = existing.data or {}
 if row.get("status") == "active" and row.get("stripe_subscription_id") == stripe_sub_id:
 return {"received": True} # already processed — idempotent no-op
 except Exception:
 pass # no row yet — proceed with update

 sub = stripe.Subscription.retrieve(stripe_sub_id)
 period_end = datetime.fromtimestamp(
 sub["current_period_end"], tz=timezone.utc
 ).isoformat()
 sb.table("subscriptions").update({
 "status": "active",
 "stripe_subscription_id": stripe_sub_id,
 "current_period_end": period_end,
 }).eq("stripe_customer_id", customer_id).execute()

 elif event["type"] == "customer.subscription.updated":
 sub = event["data"]["object"]
 customer_id = sub.get("customer")
 stripe_status = sub.get("status", "inactive")
 db_status = "active" if stripe_status == "active" else "inactive"
 sb.table("subscriptions").update({
 "status": db_status,
 }).eq("stripe_customer_id", customer_id).execute()

 elif event["type"] == "customer.subscription.deleted":
 customer_id = event["data"]["object"].get("customer")
 sb.table("subscriptions").update({
 "status": "inactive",
 }).eq("stripe_customer_id", customer_id).execute()

 return {"received": True}


# ── GET /billing/status ────────────────────────────────────────────────────────

@router.get("/status")
def billing_status(user_id: str = Depends(get_current_user)):
 """
 Return the current subscription status for the authenticated user.
 Testnet / demo bypass: always returns active for demo-user.
 """
 if user_id == "demo-user":
 return {"status": "active", "current_period_end": None}

 sb = _supabase_service()

 try:
 result = (
 sb.table("subscriptions")
 .select("status, current_period_end")
 .eq("user_id", user_id)
 .single()
 .execute()
 )
 data = result.data or {}
 except Exception:
 data = {}

 return {
 "status": data.get("status", "inactive"),
 "current_period_end": data.get("current_period_end"),
 }


# ── Stripe client helper ───────────────────────────────────────────────────────

def _get_stripe():
 """Return configured stripe module. Raises 503 if key missing."""
 import stripe
 api_key = os.getenv("STRIPE_SECRET_KEY")
 if not api_key:
 raise HTTPException(503, "STRIPE_SECRET_KEY not configured.")
 stripe.api_key = api_key
 return stripe
