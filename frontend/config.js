/**
 * frontend/config.js — Sovereign AI Context client configuration
 *
 * WALLET_API / DEMO_API: empty string = same origin as the page.
 * In production (Railway), the FastAPI server serves both the API and this
 * static frontend from the same domain, so relative paths work everywhere.
 * For local dev, override by setting these to 'http://localhost:800x'.
 *
 * WALLETCONNECT_PROJECT_ID: Get a free one at https://cloud.walletconnect.com
 * Sign in → New Project → App → copy the Project ID
 *
 * SUPABASE_ANON_KEY: public/anon key — safe to expose in frontend.
 * Find it at supabase.com → your project → Settings → API
 *
 * STRIPE_PUBLISHABLE_KEY: publishable key only — safe to expose in frontend.
 * Secret key stays in .env on the server (never in this file).
 * Find it at dashboard.stripe.com → Developers → API keys
 */

export const WALLETCONNECT_PROJECT_ID = '811ec97cb33c40e97d354123420c90fb';

// Same-origin: works in production and local dev when running a single server.
// For the two-server local demo (demo_both.bat), override these temporarily.
export const DEMO_API = '';
export const WALLET_API = '';

// ── Supabase (auth) ────────────────────────────────────────────────────────────
export const SUPABASE_URL = 'https://ywovpkkbtfmkpcodjuhx.supabase.co';
export const SUPABASE_ANON_KEY = 'sb_publishable_DZ6iuhcAHDVB7sC0IM_8WA_gq0_Yqcl';

// ── Stripe (card payments) ────────────────────────────────────────────────────
// Replace with your live publishable key from dashboard.stripe.com → Developers → API keys
export const STRIPE_PUBLISHABLE_KEY = 'pk_live_your_key_here';
