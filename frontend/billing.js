/**
 * billing.js — Subscription billing modal for Sovereign AI Context
 *
 * Payment path:
 * Stripe — redirect to hosted Stripe Checkout, return to /demo?payment=success
 * First invoice: $99 setup fee + $40 first month
 * Subsequent invoices: $40/month only
 *
 * Exports (for app.js):
 * showBillingModal() — open the billing modal
 * hideBillingModal() — close the billing modal
 * checkStripeReturn() — call on page load to detect ?payment=success redirect
 *
 * window globals (for onclick attributes):
 * window.startStripeCheckout() — POST /billing/create-checkout → redirect
 * window._afterSubscribe — callback set by app.js, called on successful subscription
 */

import { WALLET_API } from './config.js';
import { getAuthToken } from './auth.js';

function _authHeaders() {
 return {
 'Authorization': `Bearer ${getAuthToken()}`,
 'Content-Type': 'application/json',
 };
}

// ── Public API ─────────────────────────────────────────────────────────────────

export function showBillingModal() {
 const modal = document.getElementById('billing-modal');
 if (!modal) return;
 modal.style.display = 'flex';
 document.getElementById('billing-error').textContent = '';
}

export function hideBillingModal() {
 const modal = document.getElementById('billing-modal');
 if (modal) modal.style.display = 'none';
}

/**
 * Call this on page load. Returns true if returning from a successful Stripe
 * checkout (URL has ?payment=success). Cleans the param from the URL.
 */
export function checkStripeReturn() {
 const params = new URLSearchParams(window.location.search);
 if (params.get('payment') === 'success') {
 const url = new URL(window.location.href);
 url.searchParams.delete('payment');
 window.history.replaceState({}, '', url.toString());
 return true;
 }
 return false;
}

// ── Stripe checkout ────────────────────────────────────────────────────────────

window.startStripeCheckout = async function() {
 const errorEl = document.getElementById('billing-error');
 const btn = document.getElementById('btn-stripe-checkout');

 btn.disabled = true;
 btn.textContent = 'Redirecting to Stripe...';
 errorEl.textContent = '';

 try {
 const res = await fetch(`${WALLET_API}/billing/create-checkout`, {
 method: 'POST',
 headers: _authHeaders(),
 });
 const json = await res.json();
 if (!res.ok) throw new Error(json.detail || `HTTP ${res.status}`);
 window.location.href = json.checkout_url;
 } catch (err) {
 errorEl.textContent = err.message;
 btn.disabled = false;
 btn.textContent = 'Pay with Card →';
 }
};

