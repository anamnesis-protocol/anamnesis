/**
 * app.js — Sovereign AI Context Demo Frontend (ES Module)
 *
 * Sign modes:
 * HashPack — real wallet via @hashgraph/hedera-wallet-connect + WalletConnect
 * Demo Mode — operator key signs server-side (/demo/sign), no wallet required
 *
 * To use HashPack mode:
 * 1. Get a free WalletConnect project ID at https://cloud.walletconnect.com
 * 2. Set WALLETCONNECT_PROJECT_ID in frontend/config.js
 * 3. Open HashPack and scan the QR code when prompted
 */

import { WALLETCONNECT_PROJECT_ID, DEMO_API, WALLET_API } from './config.js';
import {
 initAuth,
 getAuthToken,
 checkSubscription,
 showAuthModal,
} from './auth.js';
import {
 showBillingModal,
 checkStripeReturn,
} from './billing.js';
import {
 showChat,
 hideChat,
 sendChatMessage,
 chatKeydown,
 refreshModels,
} from './chat.js';

// Route API calls to the correct server based on sign mode:
// Demo Mode → DEMO_API (testnet, port 8000 — no real HBAR cost)
// HashPack → WALLET_API (mainnet, port 8001 — real wallet)
function getApiBase() {
 return state.signMode === 'wallet' ? WALLET_API : DEMO_API;
}

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
 tokenId: null,
 challengeHex: null,
 sigHex: null,
 indexFileId: null,
 sessionId: null,
 contextSections: {},
 activeTab: null,
 signMode: 'wallet', // 'wallet' | 'demo'
};

// ── Wallet SDK (lazy loaded) ──────────────────────────────────────────────────
let dAppConnector = null;
let walletAccount = null; // '0.0.XXXXX'
let walletSdkReady = false;

async function loadWalletSDK() {
 if (walletSdkReady) return true;
 try {
 const mod = await import('https://esm.sh/@hashgraph/hedera-wallet-connect@latest');
 window._hwc = mod; // cache on window
 walletSdkReady = true;
 setNote('wallet-sdk-note', '');
 document.getElementById('btn-connect-wallet').disabled = false;
 return true;
 } catch (err) {
 setNote('wallet-sdk-note',
 'Wallet SDK failed to load. Use Demo Mode or add a WalletConnect project ID to config.js.');
 console.warn('[wallet] SDK load failed:', err);
 return false;
 }
}

async function initWallet() {
 if (!walletSdkReady) return;
 const { DAppConnector, HederaJsonRpcMethod, HederaSessionEvent, LedgerId } = window._hwc;

 const ledgerId = LedgerId.MAINNET; // HashPack mode always uses mainnet

 const metadata = {
 name: 'Sovereign AI Context',
 description: 'Patent-pending sovereign AI context system',
 url: window.location.origin,
 icons: [],
 };

 dAppConnector = new DAppConnector(
 metadata,
 ledgerId,
 WALLETCONNECT_PROJECT_ID,
 Object.values(HederaJsonRpcMethod),
 [HederaSessionEvent.ChainChanged, HederaSessionEvent.AccountsChanged],
 );

 await dAppConnector.init({ logger: 'error' });

 // Restore existing session if any
 const sessions = dAppConnector.walletConnectClient?.session?.getAll?.() ?? [];
 if (sessions.length > 0) {
 const accounts = sessions[0]?.namespaces?.hedera?.accounts ?? [];
 if (accounts.length > 0) {
 walletAccount = accounts[0].split(':').pop();
 setWalletConnected(walletAccount);
 }
 }
}

async function connectWallet() {
 if (!walletSdkReady) {
 const ok = await loadWalletSDK();
 if (!ok) return;
 }
 if (!dAppConnector) await initWallet();

 try {
 showLoading('Opening HashPack connection...');
 await dAppConnector.openModal();
 const sessions = dAppConnector.walletConnectClient?.session?.getAll?.() ?? [];
 if (sessions.length > 0) {
 const accounts = sessions[0]?.namespaces?.hedera?.accounts ?? [];
 if (accounts.length > 0) {
 walletAccount = accounts[0].split(':').pop();
 setWalletConnected(walletAccount);
 }
 }
 } catch (err) {
 showError('Wallet connection failed: ' + err.message);
 logAudit('ERROR', 'Wallet connection failed: ' + err.message, 'event-error');
 } finally {
 hideLoading();
 }
}

async function disconnectWallet() {
 if (dAppConnector) {
 try { await dAppConnector.disconnectAll(); } catch (_) {}
 }
 walletAccount = null;
 document.getElementById('wallet-connected').style.display = 'none';
 document.getElementById('wallet-disconnected').style.display = 'block';
 logAudit('WALLET_DISCONNECTED', 'HashPack disconnected');
}

function setWalletConnected(accountId) {
 document.getElementById('display-wallet-account').textContent = accountId;
 document.getElementById('wallet-disconnected').style.display = 'none';
 document.getElementById('wallet-connected').style.display = 'block';
 logAudit('WALLET_CONNECTED', `account=${accountId}`, 'event-session');
}

async function walletSign() {
 if (!state.tokenId || !state.challengeHex) { showError('Provision a vault first.'); return; }
 if (!walletAccount) { showError('Connect HashPack first.'); return; }

 showLoading('Waiting for HashPack signature...');
 activateStep('sign');
 logAudit('WALLET_SIGN', `token=${state.tokenId} account=${walletAccount}`);

 try {
 // signMessage signs the challenge hex string with the wallet's Ed25519 key.
 // Ed25519 is deterministic: same key + same message → same 64-byte signature every time.
 // This means the same wallet sig encrypts the vault AND decrypts it later — no key escrow.
 const result = await dAppConnector.signMessage({
 signerAccountId: `hedera:mainnet:${walletAccount}`,
 message: state.challengeHex,
 });

 const sigBytes = extractSignatureBytes(result);
 state.sigHex = toHex(sigBytes);

 document.getElementById('display-sig').textContent = state.sigHex;
 document.getElementById('display-sig').title = state.sigHex;

 updateKDF(state.tokenId, state.sigHex);
 completeStep('sign');
 logAudit('CHALLENGE_SIGNED', `sig=${state.sigHex.substring(0, 16)}... (HashPack)`, 'event-session');

 unlockStep('complete');
 setStatus('complete', 'READY', 'status-active');
 document.getElementById('step-complete').classList.remove('locked');

 } catch (err) {
 setStatus('sign', 'ERROR', 'status-error');
 logAudit('ERROR', err.message, 'event-error');
 showError(err.message);
 } finally {
 hideLoading();
 }
}

/**
 * Extract raw signature bytes from a hedera-wallet-connect signMessage result.
 * The result is a SignatureMap protobuf. Try several possible decoded shapes.
 */
function extractSignatureBytes(result) {
 // Shape 1: decoded object with sigPair array (most common from hedera-wallet-connect)
 if (result?.sigPair?.length > 0) {
 const pair = result.sigPair[0];
 const sig = pair.ed25519 ?? pair.ecdsaSecp256k1 ?? pair.ecdsa_secp256k1;
 if (sig?.length) return new Uint8Array(sig);
 }
 // Shape 2: array of SignatureMap objects
 if (Array.isArray(result) && result[0]?.sigPair?.length > 0) {
 const pair = result[0].sigPair[0];
 const sig = pair.ed25519 ?? pair.ecdsaSecp256k1 ?? pair.ecdsa_secp256k1;
 if (sig?.length) return new Uint8Array(sig);
 }
 // Shape 3: raw 64-byte Uint8Array
 if (result instanceof Uint8Array && result.length === 64) return result;
 if (result?.bytes?.length === 64) return new Uint8Array(result.bytes);
 // Shape 4: hex string (128 chars = 64 bytes)
 if (typeof result === 'string' && /^[0-9a-f]{128}$/i.test(result)) {
 return new Uint8Array(result.match(/.{2}/g).map(b => parseInt(b, 16)));
 }
 throw new Error(
 'Cannot extract signature from wallet result — unexpected format: ' +
 JSON.stringify(result).substring(0, 200)
 );
}

function toHex(bytes) {
 return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

// ── Sign mode toggle ──────────────────────────────────────────────────────────

function setSignMode(mode) {
 state.signMode = mode;
 document.getElementById('mode-wallet').style.display = mode === 'wallet' ? 'block' : 'none';
 document.getElementById('mode-demo').style.display = mode === 'demo' ? 'block' : 'none';
 document.getElementById('toggle-wallet').classList.toggle('active', mode === 'wallet');
 document.getElementById('toggle-demo').classList.toggle('active', mode === 'demo');
}

function setNote(id, text) {
 const el = document.getElementById(id);
 if (el) el.textContent = text;
}

// ── Step management ───────────────────────────────────────────────────────────

function activateStep(id) {
 const el = document.getElementById(`step-${id}`);
 if (!el) return;
 el.classList.remove('locked');
 el.classList.add('active');
 setStatus(id, 'WORKING', 'status-active');
}

function completeStep(id) {
 const el = document.getElementById(`step-${id}`);
 if (!el) return;
 el.classList.remove('active', 'locked');
 el.classList.add('done');
 setStatus(id, 'DONE', 'status-done');
}

function setStatus(id, text, cls) {
 const el = document.getElementById(`status-${id}`);
 if (!el) return;
 el.textContent = text;
 el.className = `step-status ${cls || ''}`;
}

function unlockStep(id) {
 const el = document.getElementById(`step-${id}`);
 if (!el) return;
 el.classList.remove('locked');
 el.classList.add('active');
}

// ── Loading / Error ───────────────────────────────────────────────────────────

function showLoading(text) {
 document.getElementById('loading-text').textContent = text || 'Working...';
 document.getElementById('loading').style.display = 'flex';
}

function hideLoading() {
 document.getElementById('loading').style.display = 'none';
}

function showError(msg) {
 const toast = document.getElementById('error-toast');
 toast.textContent = msg;
 toast.classList.add('show');
 setTimeout(() => toast.classList.remove('show'), 5000);
}

// ── Audit log ─────────────────────────────────────────────────────────────────

function logAudit(type, detail, cls = '') {
 const log = document.getElementById('audit-log');
 const placeholder = log.querySelector('.audit-placeholder');
 if (placeholder) placeholder.remove();

 const now = new Date().toLocaleTimeString('en-US', { hour12: false });
 const ev = document.createElement('div');
 ev.className = `audit-event ${cls}`;
 ev.innerHTML = `
 <span class="audit-time">${now}</span>
 <span class="audit-type">${type}</span>
 <span class="audit-detail">${detail}</span>
 `;
 log.appendChild(ev);
 log.scrollTop = log.scrollHeight;
}

// ── KDF visualization ─────────────────────────────────────────────────────────

function updateKDF(tokenId, sigHex, showDiscard = false) {
 document.getElementById('kdf-token-val').textContent =
 tokenId ? tokenId.substring(0, 16) + '...' : '—';
 document.getElementById('kdf-sig-val').textContent =
 sigHex ? sigHex.substring(0, 16) + '...' : '—';
 document.getElementById('kdf-key-val').textContent =
 (tokenId && sigHex) ? 'derived...' : '—';
 document.getElementById('kdf-discard').textContent =
 showDiscard ? '🗑 KEY DISCARDED' : '';
}

// ── Sections display ──────────────────────────────────────────────────────────

function showSectionsEncrypted(sectionNames) {
 document.getElementById('sections-list').innerHTML = sectionNames.map(name => `
 <div class="section-item encrypted" id="sec-${name}">
 <span class="section-icon">🔐</span>
 <span class="section-name">${name}</span>
 <span class="section-status">encrypted on HFS</span>
 </div>
 `).join('');
}

function showSectionsDecrypted(sections) {
 document.getElementById('sections-list').innerHTML = Object.entries(sections).map(([name, content]) => `
 <div class="section-item decrypted" id="sec-${name}">
 <span class="section-icon">✅</span>
 <span class="section-name">${name}</span>
 <span class="section-status">${content.length.toLocaleString()} chars</span>
 </div>
 `).join('');
}

// ── Context viewer ────────────────────────────────────────────────────────────

function renderContext(sections) {
 const tabs = document.getElementById('context-tabs');
 const names = Object.keys(sections);
 if (names.length === 0) return;

 tabs.innerHTML = names.map((name, i) => `
 <button class="context-tab ${i === 0 ? 'active' : ''}"
 onclick="switchTab('${name}')"
 id="tab-${name}">
 ${name}
 </button>
 `).join('');

 state.activeTab = names[0];
 document.getElementById('context-content').innerHTML =
 `<pre class="context-text">${escapeHtml(sections[names[0]])}</pre>`;
}

function switchTab(name) {
 document.querySelectorAll('.context-tab').forEach(t => t.classList.remove('active'));
 document.getElementById(`tab-${name}`)?.classList.add('active');
 document.getElementById('context-content').innerHTML =
 `<pre class="context-text">${escapeHtml(state.contextSections[name] || '')}</pre>`;
 state.activeTab = name;
}

function escapeHtml(str) {
 return str
 .replace(/&/g, '&amp;')
 .replace(/</g, '&lt;')
 .replace(/>/g, '&gt;');
}

// ── API calls ─────────────────────────────────────────────────────────────────

async function apiFetch(path, body = null, method = null) {
 // Include Authorization header on mainnet (wallet mode) so the subscription
 // gate can verify the JWT on /user/provision/start.
 const headers = { 'Content-Type': 'application/json' };
 if (state.signMode === 'wallet') {
 const token = getAuthToken();
 if (token) headers['Authorization'] = `Bearer ${token}`;
 }

 const m = method ?? (body ? 'POST' : 'GET');
 const opts = { method: m, headers };
 if (body) opts.body = JSON.stringify(body);
 const res = await fetch(`${getApiBase()}${path}`, opts);
 const json = await res.json();
 if (!res.ok) throw new Error(json.detail || `HTTP ${res.status}`);
 return json;
}

// ── Settings Modal (API Keys) ─────────────────────────────────────────────────

const _PROVIDERS = [
 { id: 'openai', label: 'OpenAI', placeholder: 'sk-...', type: 'password' },
 { id: 'anthropic', label: 'Anthropic', placeholder: 'sk-ant-...', type: 'password' },
 { id: 'google', label: 'Google', placeholder: 'AIza...', type: 'password' },
 { id: 'mistral', label: 'Mistral', placeholder: 'your-mistral-api-key', type: 'password' },
 { id: 'groq', label: 'Groq', placeholder: 'gsk_...', type: 'password' },
 { id: 'ollama', label: 'Ollama', placeholder: 'http://localhost:11434', type: 'text' },
];

let _configuredProviders = []; // providers with a readable key (from GET /user/keys)
let _corruptedProviders = []; // providers where decryption failed — user must re-enter

async function openApiKeysModal() {
 const modal = document.getElementById('settings-modal');
 modal.style.display = 'flex';
 document.getElementById('settings-key-list').innerHTML =
 '<div class="settings-loading">Loading...</div>';

 try {
 const data = await apiFetch('/user/keys');
 if (data.demo) {
 document.getElementById('settings-key-list').innerHTML =
 '<div class="settings-demo-notice">' +
 '⚡ Demo mode — keys are sourced from server environment. ' +
 'Log in to manage your own keys.' +
 '</div>';
 return;
 }
 _configuredProviders = data.configured || [];
 _corruptedProviders = data.corrupted_providers || [];
 _renderKeyRows(_configuredProviders, _corruptedProviders);
 } catch (_) {
 _configuredProviders = [];
 _corruptedProviders = [];
 _renderKeyRows([], []);
 }
}

function closeApiKeysModal() {
 document.getElementById('settings-modal').style.display = 'none';
}

function _renderKeyRows(configured, corrupted = []) {
 const container = document.getElementById('settings-key-list');
 container.innerHTML = _PROVIDERS.map(p => {
 const isConfigured = configured.includes(p.id);
 const isCorrupted = corrupted.includes(p.id);

 let statusIcon, statusClass, actionHtml;
 if (isCorrupted) {
 // Key exists in DB but cannot be decrypted — prompt re-entry
 statusIcon = '⚠';
 statusClass = 'corrupted';
 actionHtml =
 `<input type="${p.type}" class="key-input" id="key-${p.id}"` +
 ` placeholder="${p.placeholder}" autocomplete="off" />` +
 `<button class="btn-primary key-save-btn" onclick="saveApiKey('${p.id}')">Re-enter</button>`;
 } else if (isConfigured) {
 statusIcon = '✅';
 statusClass = 'configured';
 actionHtml =
 `<input type="${p.type}" class="key-input" id="key-${p.id}"` +
 ` placeholder="${p.placeholder}" autocomplete="off" />` +
 `<button class="btn-primary key-save-btn" onclick="saveApiKey('${p.id}')">Update</button>` +
 `<button class="btn-ghost key-del-btn" onclick="deleteApiKey('${p.id}')">Remove</button>`;
 } else {
 statusIcon = '✗';
 statusClass = '';
 actionHtml =
 `<input type="${p.type}" class="key-input" id="key-${p.id}"` +
 ` placeholder="${p.placeholder}" autocomplete="off" />` +
 `<button class="btn-primary key-save-btn" onclick="saveApiKey('${p.id}')">Save</button>`;
 }

 return `
 <div class="key-row${isCorrupted ? ' key-row--corrupted' : ''}">
 <div class="key-provider-label">
 <span class="key-status ${statusClass}">${statusIcon}</span>
 ${p.label}${isCorrupted ? ' <span class="key-corrupted-hint">re-enter key</span>' : ''}
 </div>
 ${actionHtml}
 </div>`;
 }).join('');
}

async function saveApiKey(provider) {
 const input = document.getElementById(`key-${provider}`);
 const key = input ? input.value.trim() : '';
 if (!key) { showError('Enter a key first.'); return; }

 try {
 await apiFetch(`/user/keys/${provider}`, { key });
 input.value = '';
 // Move from corrupted → configured if it was corrupted before
 _corruptedProviders = _corruptedProviders.filter(p => p !== provider);
 if (!_configuredProviders.includes(provider)) _configuredProviders.push(provider);
 _renderKeyRows(_configuredProviders, _corruptedProviders);
 logAudit('KEY_SAVED', `${provider} API key encrypted and stored`);
 // Refresh model dropdown if a session is active
 if (state.sessionId) await refreshModels();
 } catch (err) {
 showError(err.message);
 }
}

async function deleteApiKey(provider) {
 try {
 await apiFetch(`/user/keys/${provider}`, null, 'DELETE');
 _configuredProviders = _configuredProviders.filter(p => p !== provider);
 _corruptedProviders = _corruptedProviders.filter(p => p !== provider);
 _renderKeyRows(_configuredProviders, _corruptedProviders);
 logAudit('KEY_DELETED', `${provider} API key removed`);
 if (state.sessionId) await refreshModels();
 } catch (err) {
 showError(err.message);
 }
}

// ── Step 1: Provision vault ───────────────────────────────────────────────────

async function startProvision() {
 // ── Paywall gate (mainnet / HashPack mode only) ────────────────────────────
 // Demo Mode (testnet) bypasses billing — the backend enforce this too.
 if (state.signMode === 'wallet') {
 const token = getAuthToken();
 if (!token) {
 // Not logged in — show auth modal, retry startProvision after login
 window._afterAuth = startProvision;
 showAuthModal();
 return;
 }

 showLoading('Checking subscription...');
 try {
 const sub = await checkSubscription();
 if (sub.status !== 'active') {
 hideLoading();
 // No active subscription — show billing modal, retry after subscribe
 window._afterSubscribe = startProvision;
 showBillingModal();
 return;
 }
 } catch (_) {
 hideLoading();
 showError('Could not verify subscription — please try again.');
 return;
 }
 hideLoading();
 }
 // ── End paywall gate ───────────────────────────────────────────────────────

 const accountId = document.getElementById('account-id').value.trim();
 const companionName = document.getElementById('companion-name').value.trim();
 if (!accountId) { showError('Enter your name so your AI knows what to call you.'); return; }
 if (!companionName) { showError('Give your AI a name to continue.'); return; }

 showLoading('Minting context token on Hedera...');
 activateStep('provision');
 logAudit('PROVISION_START', `account=${accountId} companion=${companionName}`);

 try {
 const data = await apiFetch('/user/provision/start', { account_id: accountId, companion_name: companionName });

 state.tokenId = data.token_id;
 state.challengeHex = data.challenge_hex;

 document.getElementById('display-token-id').textContent = data.token_id;
 document.getElementById('display-challenge').textContent = data.challenge_hex;
 document.getElementById('display-challenge').title = data.challenge_hex;

 updateKDF(data.token_id, null);
 completeStep('provision');
 logAudit('CONTEXT_TOKEN_MINTED', `token=${data.token_id}`, 'event-session');
 logAudit('CHALLENGE_ISSUED', `expires=${new Date(data.expires_at).toLocaleTimeString()}`);

 unlockStep('sign');
 setStatus('sign', 'READY', 'status-active');
 document.getElementById('step-sign').classList.remove('locked');

 } catch (err) {
 setStatus('provision', 'ERROR', 'status-error');
 logAudit('ERROR', err.message, 'event-error');
 showError(err.message);
 } finally {
 hideLoading();
 }
}

// ── Step 2a: Demo sign (operator key, no wallet) ──────────────────────────────

async function demoSign() {
 if (!state.tokenId) { showError('Provision a vault first.'); return; }

 showLoading('Signing challenge with demo key...');
 activateStep('sign');
 logAudit('DEMO_SIGN', `token=${state.tokenId}`);

 try {
 const data = await apiFetch('/demo/sign', { token_id: state.tokenId });
 state.sigHex = data.signature_hex;

 document.getElementById('display-sig').textContent = data.signature_hex;
 document.getElementById('display-sig').title = data.signature_hex;

 updateKDF(state.tokenId, data.signature_hex);
 completeStep('sign');
 logAudit('CHALLENGE_SIGNED', `sig=${data.signature_hex.substring(0, 16)}... (demo key)`, 'event-session');

 unlockStep('complete');
 setStatus('complete', 'READY', 'status-active');
 document.getElementById('step-complete').classList.remove('locked');

 } catch (err) {
 setStatus('sign', 'ERROR', 'status-error');
 logAudit('ERROR', err.message, 'event-error');
 showError(err.message);
 } finally {
 hideLoading();
 }
}

// ── Step 3: Complete provisioning ─────────────────────────────────────────────

async function completeProvision() {
 if (!state.tokenId || !state.sigHex) { showError('Sign the challenge first.'); return; }

 showLoading('Encrypting vault and pushing to HFS...');
 activateStep('complete');
 logAudit('VAULT_PUSH', `token=${state.tokenId}`);

 try {
 const data = await apiFetch('/user/provision/complete', {
 token_id: state.tokenId,
 wallet_signature_hex: state.sigHex,
 });

 state.indexFileId = data.index_file_id;
 document.getElementById('display-index').textContent = data.index_file_id;
 document.getElementById('display-registered').textContent =
 data.vault_registered ? '✅ Registered in ContextValidator contract' : '⚠ HFS only (contract pending)';

 showSectionsEncrypted(data.sections_pushed);
 completeStep('complete');
 logAudit('VAULT_PROVISIONED', `sections=[${data.sections_pushed.join(', ')}]`, 'event-session');
 logAudit('CONTRACT_REGISTERED', `index=${data.index_file_id}`, 'event-session');

 unlockStep('session');
 setStatus('session', 'READY', 'status-active');
 document.getElementById('step-session').classList.remove('locked');

 } catch (err) {
 setStatus('complete', 'ERROR', 'status-error');
 logAudit('ERROR', err.message, 'event-error');
 showError(err.message);
 } finally {
 hideLoading();
 }
}

// ── Step 4: Open session ──────────────────────────────────────────────────────

async function openSession() {
 if (!state.tokenId || !state.sigHex) { showError('Complete provisioning first.'); return; }

 showLoading('Deriving key → decrypting HFS → injecting context...');
 activateStep('session');
 logAudit('SESSION_OPEN', `token=${state.tokenId}`);

 try {
 const data = await apiFetch('/session/open', {
 token_id: state.tokenId,
 wallet_signature_hex: state.sigHex,
 });

 state.sessionId = data.session_id;
 state.contextSections = data.context_sections;

 document.getElementById('display-session-id').textContent = data.session_id;
 document.getElementById('display-expires').textContent =
 new Date(data.expires_at).toLocaleString();

 updateKDF(state.tokenId, state.sigHex, true);
 showSectionsDecrypted(data.context_sections);
 renderContext(data.context_sections);

 completeStep('session');
 logAudit('SESSION_STARTED', `session=${data.session_id.substring(0, 8)}...`, 'event-session');
 logAudit('HCS_LOGGED', 'SESSION_STARTED anchored on Hedera Consensus Service');

 unlockStep('active');
 setStatus('active', 'LIVE', 'status-active');
 document.getElementById('step-active').classList.remove('locked');
 document.getElementById('status-active').classList.add('pulse');

 // Show AI chat panel — session context is now live server-side
 const authHdr = {};
 if (state.signMode === 'wallet') {
 const token = getAuthToken();
 if (token) authHdr['Authorization'] = `Bearer ${token}`;
 }
 showChat(data.session_id, getApiBase(), authHdr);

 } catch (err) {
 setStatus('session', 'ERROR', 'status-error');
 logAudit('ERROR', err.message, 'event-error');
 showError(err.message);
 } finally {
 hideLoading();
 }
}

// ── Step 5: Close session ─────────────────────────────────────────────────────
// Patent sub-claim: Session-Scoped Key Lifecycle
//
// On close we send back the current contextSections so the server can:
// 1. Diff against session-open hashes
// 2. Re-encrypt changed sections with the stored session key
// 3. Push updated ciphertext back to Hedera HFS
// 4. Zero the session key and index key, evict session
//
// After the server confirms, we zero contextSections locally.
// Decrypted content exists locally ONLY within the open-to-close window.

async function closeSession() {
 if (!state.sessionId) { showError('No active session.'); return; }

 showLoading('Re-encrypting → pushing to Hedera → zeroing local...');
 logAudit('SESSION_CLOSE', `session=${state.sessionId.substring(0, 8)}...`);

 try {
 const data = await apiFetch('/session/close', {
 session_id: state.sessionId,
 updated_sections: state.contextSections, // send current content back for re-encryption
 });

 // ── Vault write-back confirmed ────────────────────────────────────────────
 if (data.vault_updated) {
 logAudit(
 'VAULT_UPDATED',
 `changed=[${data.changed_sections.join(', ')}] → re-encrypted & pushed to HFS`,
 'event-session',
 );
 } else {
 logAudit('VAULT_UNCHANGED', 'No sections modified — Hedera push skipped');
 }

 if (data.hcs_logged) {
 logAudit('HCS_LOGGED', 'SESSION_ENDED anchored on Hedera Consensus Service', 'event-session');
 }

 logAudit(
 'SESSION_ENDED',
 `closed_at=${new Date(data.closed_at).toLocaleTimeString()}`,
 'event-session',
 );

 // ── Zero local decrypted content ─────────────────────────────────────────
 // Overwrite each section string before clearing the object reference.
 // Server-side keys were zeroed by close_session() on the backend.
 for (const key of Object.keys(state.contextSections)) {
 state.contextSections[key] = '\x00'.repeat(state.contextSections[key]?.length ?? 0);
 }
 state.contextSections = {};
 state.sessionId = null;

 // Hide chat panel and zero conversation state
 hideChat();

 // Update UI — sections back to encrypted state
 setStatus('active', 'CLOSED', 'status-done');
 document.getElementById('status-active').classList.remove('pulse');
 document.getElementById('context-tabs').innerHTML = '';
 document.getElementById('context-content').innerHTML =
 '<span class="context-placeholder">Session closed — context zeroed locally, encrypted on Hedera.</span>';
 showSectionsEncrypted(data.changed_sections.length > 0
 ? data.changed_sections
 : Object.keys(state.start_hashes ?? {}));

 updateKDF(null, null, false);

 } catch (err) {
 logAudit('ERROR', err.message, 'event-error');
 showError(err.message);
 } finally {
 hideLoading();
 }
}

// ── Expose handlers to window (required for ES module onclick attributes) ─────
Object.assign(window, {
 startProvision,
 walletSign,
 demoSign,
 connectWallet,
 disconnectWallet,
 setSignMode,
 completeProvision,
 openSession,
 closeSession,
 switchTab,
 // Chat handlers — called from chat panel onclick/onkeydown
 sendChatMessage,
 chatKeydown,
 // Settings modal — called from ⚙ button and modal HTML
 openApiKeysModal,
 closeApiKeysModal,
 saveApiKey,
 deleteApiKey,
 // Expose for use by auth.js / billing.js callbacks
 hideLoading,
 showError,
});

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
 setSignMode('wallet');
 document.getElementById('btn-connect-wallet').disabled = true;
 setNote('wallet-sdk-note', 'Loading wallet SDK...');

 document.getElementById('step-provision').classList.remove('locked');
 document.getElementById('step-provision').classList.add('active');
 setStatus('provision', 'READY', 'status-active');
 logAudit('DEMO_READY', 'Sovereign AI Context — patent pending US 64/007,132');

 // Restore auth state from localStorage (shows email in header if logged in)
 initAuth();

 // Check if returning from successful Stripe checkout
 if (checkStripeReturn()) {
 logAudit('PAYMENT_SUCCESS', 'Stripe subscription activated — vault provisioning unlocked');
 }

 // Load wallet SDK in background — demo mode works regardless
 const sdkOk = await loadWalletSDK();
 if (sdkOk) {
 if (WALLETCONNECT_PROJECT_ID !== 'YOUR_PROJECT_ID_HERE') {
 setNote('wallet-sdk-note', 'Ready — click Connect HashPack');
 await initWallet().catch(err =>
 console.warn('[wallet] Pre-init failed (will retry on connect):', err)
 );
 } else {
 setNote('wallet-sdk-note', 'Add your WalletConnect project ID to frontend/config.js to use HashPack');
 }
 }
});
