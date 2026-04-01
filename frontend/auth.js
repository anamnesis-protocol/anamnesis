/**
 * auth.js — Authentication modal for Sovereign AI Context
 *
 * Handles sign-up / log-in against our backend's /auth/* endpoints.
 * Stores the Supabase JWT in localStorage so the session survives page refresh.
 *
 * Exports (for app.js):
 * initAuth() — restore session from localStorage on page load
 * getAuthToken() — return stored JWT string (or null)
 * getUserEmail() — return stored email (or null)
 * checkSubscription() — GET /billing/status → { status, current_period_end }
 * showAuthModal() — open the auth modal
 * hideAuthModal() — close the auth modal
 * logout() — clear token + update UI
 *
 * window globals (for onclick attributes):
 * window.switchAuthTab(tab) — 'login' | 'signup'
 * window.submitAuth() — form submit handler
 * window._sacLogout() — sign-out handler
 * window._afterAuth — callback set by app.js, called after login
 */

import { WALLET_API } from './config.js';

// ── Token storage ──────────────────────────────────────────────────────────────

let _authToken = null;
let _userEmail = null;

export function getAuthToken() {
 if (_authToken) return _authToken;
 _authToken = localStorage.getItem('sac_auth_token');
 return _authToken;
}

export function getUserEmail() {
 return _userEmail || localStorage.getItem('sac_user_email') || null;
}

function _setAuth(token, email) {
 _authToken = token;
 _userEmail = email;
 if (token) {
 localStorage.setItem('sac_auth_token', token);
 localStorage.setItem('sac_user_email', email || '');
 } else {
 localStorage.removeItem('sac_auth_token');
 localStorage.removeItem('sac_user_email');
 }
}

// ── Public API ─────────────────────────────────────────────────────────────────

export function logout() {
 _setAuth(null, null);
 _updateAuthIndicator(null);
}

export async function checkSubscription() {
 const token = getAuthToken();
 if (!token) return { status: 'unauthenticated' };
 try {
 const res = await fetch(`${WALLET_API}/billing/status`, {
 headers: { 'Authorization': `Bearer ${token}` },
 });
 if (!res.ok) return { status: 'inactive' };
 return await res.json();
 } catch {
 return { status: 'error' };
 }
}

export function showAuthModal() {
 const modal = document.getElementById('auth-modal');
 if (!modal) return;
 modal.style.display = 'flex';
 document.getElementById('auth-error').textContent = '';
 document.getElementById('auth-email').value = '';
 document.getElementById('auth-password').value = '';
 window.switchAuthTab('login');
 setTimeout(() => document.getElementById('auth-email').focus(), 50);
}

export function hideAuthModal() {
 const modal = document.getElementById('auth-modal');
 if (modal) modal.style.display = 'none';
}

export function initAuth() {
 const token = getAuthToken();
 const email = getUserEmail();
 if (token && email) {
 _authToken = token;
 _userEmail = email;
 _updateAuthIndicator(email);
 }
}

// ── Auth indicator (header) ────────────────────────────────────────────────────

function _updateAuthIndicator(email) {
 const el = document.getElementById('auth-indicator');
 if (!el) return;
 if (email) {
 el.innerHTML = `
 <span class="auth-dot">●</span>
 <span class="auth-email">${_escapeHtml(email)}</span>
 <button class="btn-auth-signout" onclick="window._sacLogout()">Sign out</button>
 `;
 el.style.display = 'flex';
 } else {
 el.style.display = 'none';
 }
}

function _escapeHtml(str) {
 return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Modal tab switching ────────────────────────────────────────────────────────

window.switchAuthTab = function(tab) {
 const modal = document.getElementById('auth-modal');
 const loginTab = document.getElementById('auth-tab-login');
 const signupTab = document.getElementById('auth-tab-signup');
 const submitBtn = document.getElementById('btn-auth-submit');
 const errorEl = document.getElementById('auth-error');

 if (!modal) return;
 modal.dataset.mode = tab;
 errorEl.textContent = '';

 if (tab === 'login') {
 loginTab?.classList.add('active');
 signupTab?.classList.remove('active');
 if (submitBtn) submitBtn.textContent = 'Log In';
 } else {
 signupTab?.classList.add('active');
 loginTab?.classList.remove('active');
 if (submitBtn) submitBtn.textContent = 'Create Account';
 }
};

// ── Form submit ────────────────────────────────────────────────────────────────

window.submitAuth = async function() {
 const email = document.getElementById('auth-email').value.trim();
 const password = document.getElementById('auth-password').value;
 const errorEl = document.getElementById('auth-error');
 const submitBtn = document.getElementById('btn-auth-submit');
 const mode = document.getElementById('auth-modal').dataset.mode || 'login';

 if (!email || !password) {
 errorEl.style.color = 'var(--red)';
 errorEl.textContent = 'Email and password are required.';
 return;
 }

 submitBtn.disabled = true;
 submitBtn.textContent = mode === 'login' ? 'Logging in...' : 'Creating account...';
 errorEl.textContent = '';

 try {
 const endpoint = mode === 'login' ? '/auth/login' : '/auth/signup';
 const res = await fetch(`${WALLET_API}${endpoint}`, {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ email, password }),
 });
 const data = await res.json();

 if (!res.ok) {
 throw new Error(data.detail || `HTTP ${res.status}`);
 }

 if (data.access_token) {
 // Signed in immediately (or email confirmation disabled)
 _setAuth(data.access_token, data.email);
 _updateAuthIndicator(data.email);
 hideAuthModal();

 // Fire post-auth callback if set by app.js
 if (window._afterAuth) {
 const cb = window._afterAuth;
 window._afterAuth = null;
 cb();
 }
 } else if (data.confirm_email) {
 // Email confirmation required
 errorEl.style.color = 'var(--teal)';
 errorEl.textContent = 'Check your inbox to confirm your account, then log in here.';
 window.switchAuthTab('login');
 } else {
 throw new Error('Unexpected response — try again.');
 }

 } catch (err) {
 errorEl.style.color = 'var(--red)';
 errorEl.textContent = err.message;
 } finally {
 submitBtn.disabled = false;
 submitBtn.textContent = mode === 'login' ? 'Log In' : 'Create Account';
 }
};

// ── Sign-out ───────────────────────────────────────────────────────────────────

window._sacLogout = function() {
 logout();
};
