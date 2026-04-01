/**
 * chat.js — Sovereign AI Context chat UI
 *
 * Exported API:
 * showChat(sessionId, apiBase, authHeaders) → load models, reveal panel
 * hideChat() → hide panel, zero state
 * sendChatMessage() → read input, stream SSE response
 * chatKeydown(event) → Enter → send, Shift+Enter → newline
 * refreshModels() → re-fetch model list (called after key save/delete)
 *
 * Patent note (Claim 14 in action):
 * The server injects the decrypted harness context as the system prompt for
 * whichever model the user selects. The client never re-sends the context —
 * only session_id + message + model. Same harness, any AI model.
 */

// ── Module state ──────────────────────────────────────────────────────────────

let _sessionId = null;
let _apiBase = null;
let _authHeaders = {};
let _history = []; // [{role, content}] — in-memory conversation turns
let _streaming = false;
let _models = [];

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Show the chat panel and load available AI models from the server.
 * Called immediately after /session/open succeeds.
 */
export async function showChat(sessionId, apiBase, authHeaders = {}) {
 _sessionId = sessionId;
 _apiBase = apiBase;
 _authHeaders = authHeaders;
 _history = [];
 _streaming = false;

 const panel = document.getElementById('chat-panel');
 panel.style.display = 'block';

 await _loadModels();

 setTimeout(() => {
 const input = document.getElementById('chat-input');
 if (input) input.focus();
 }, 100);
}

/**
 * Hide the chat panel and zero all state.
 * Called after /session/close completes.
 */
export function hideChat() {
 const panel = document.getElementById('chat-panel');
 if (panel) panel.style.display = 'none';
 _resetState();
}

/**
 * Clear messages and history without hiding the panel.
 */
export function resetChat() {
 _history = [];
 _streaming = false;
 const msgs = document.getElementById('chat-messages');
 if (msgs) msgs.innerHTML = '';
 const input = document.getElementById('chat-input');
 if (input) input.value = '';
}

// ── Model loading ─────────────────────────────────────────────────────────────

async function _loadModels() {
 const select = document.getElementById('model-select');
 const sendBtn = document.getElementById('btn-send-chat');
 select.innerHTML = '<option>Loading models...</option>';
 sendBtn.disabled = true;

 try {
 const url = _sessionId
 ? `${_apiBase}/chat/models?session_id=${encodeURIComponent(_sessionId)}`
 : `${_apiBase}/chat/models`;
 const res = await fetch(url, { headers: _authHeaders });
 const data = await res.json();

 if (!data.models || data.models.length === 0) {
 select.innerHTML = '<option value="">No models available</option>';
 _appendSystemMessage(
 '⚠ ' + (data.message ||
 'No AI models available. Click ⚙ to add your API keys, or contact support.')
 );
 return;
 }

 _models = data.models;
 select.innerHTML = _models
 .map(m => `<option value="${m.id}">${m.display} (${m.provider})</option>`)
 .join('');

 select.onchange = () => { /* selection read at send time */ };

 sendBtn.disabled = false;
 _appendSystemMessage(
 '🔐 Harness active. Your directives are loaded and encrypted. ' +
 'You\'re in command — AI executes your orders. Everything stays on Hedera. We see nothing.'
 );

 } catch (err) {
 select.innerHTML = '<option value="">Error loading models</option>';
 _appendSystemMessage(`⚠ Could not load models: ${err.message}`);
 }
}

/**
 * Re-fetch the model list and update the dropdown.
 * Called from app.js after the user saves or removes an API key.
 */
export async function refreshModels() {
 await _loadModels();
}

// ── Send message ──────────────────────────────────────────────────────────────

/**
 * Read the chat input, send to /chat/message, stream SSE tokens into an AI bubble.
 * Exposed to window via app.js (required for onclick in non-module HTML).
 */
export async function sendChatMessage() {
 if (_streaming) return;
 if (!_sessionId) { _appendSystemMessage('⚠ No active session.'); return; }

 const input = document.getElementById('chat-input');
 const select = document.getElementById('model-select');
 const message = input.value.trim();
 const modelId = select.value;

 if (!message) return;
 if (!modelId) { _appendSystemMessage('⚠ Select an AI model first.'); return; }

 // Clear input and show user bubble
 input.value = '';
 input.style.height = 'auto';
 _appendUserBubble(message);

 // ── Model recommendation (non-blocking, pure Python — <10 ms) ──────────
 // Classify the task and advise before the response streams.
 // This is the core router directive: always steer toward the best model.
 const recommendation = await _getRecommendation(message, modelId);
 _renderRecommendation(recommendation, modelId);

 // Lock send button during streaming
 _streaming = true;
 const sendBtn = document.getElementById('btn-send-chat');
 sendBtn.disabled = true;
 sendBtn.textContent = '...';

 // Create AI bubble to receive streamed tokens
 const { contentEl, cursorEl, wrapperEl } = _appendAIBubble();
 let fullText = '';

 try {
 const res = await fetch(`${_apiBase}/chat/message`, {
 method: 'POST',
 headers: { 'Content-Type': 'application/json', ..._authHeaders },
 body: JSON.stringify({
 session_id: _sessionId,
 message,
 model: modelId,
 history: _history,
 }),
 });

 if (!res.ok) {
 const err = await res.json().catch(() => ({}));
 throw new Error(err.detail || `HTTP ${res.status}`);
 }

 // Read SSE stream via ReadableStream (works with POST unlike EventSource)
 const reader = res.body.getReader();
 const decoder = new TextDecoder();
 let buf = '';

 outer: while (true) {
 const { done, value } = await reader.read();
 if (done) break;

 buf += decoder.decode(value, { stream: true });
 const lines = buf.split('\n');
 buf = lines.pop(); // retain incomplete line

 for (const line of lines) {
 if (!line.startsWith('data: ')) continue;
 try {
 const data = JSON.parse(line.slice(6));
 if (data.done) break outer;
 if (data.content) {
 fullText += data.content;
 contentEl.textContent = fullText;
 _scrollBottom();
 }
 } catch (_) { /* skip malformed SSE frame */ }
 }
 }

 // Persist to in-memory history for next turn
 _history.push({ role: 'user', content: message });
 _history.push({ role: 'assistant', content: fullText });

 } catch (err) {
 contentEl.textContent = `[Error: ${err.message}]`;
 wrapperEl.classList.add('chat-bubble-error');
 } finally {
 cursorEl.remove();
 _streaming = false;
 sendBtn.disabled = false;
 sendBtn.textContent = 'Send';
 _scrollBottom();
 }
}

// ── Model recommendation ───────────────────────────────────────────────────

/**
 * Ask the server to classify the message and recommend the best model.
 * Pure Python rule-based — <10 ms — called before streaming begins.
 *
 * @param {string} message
 * @param {string} modelId — currently selected model
 * @returns {Promise<object|null>}
 */
async function _getRecommendation(message, modelId) {
 if (!_sessionId || !_apiBase) return null;
 try {
 const res = await fetch(`${_apiBase}/chat/recommend`, {
 method: 'POST',
 headers: { 'Content-Type': 'application/json', ..._authHeaders },
 body: JSON.stringify({
 session_id: _sessionId,
 message,
 current_model: modelId,
 }),
 });
 if (!res.ok) return null;
 return await res.json();
 } catch (_) {
 return null; // recommendation is non-blocking — never fail the chat
 }
}

/**
 * Evaluate a recommendation result and inject a chip into the chat if warranted.
 *
 * Rules:
 * cannot_complete → ⛔ warning (task requires model capability not configured)
 * !current_is_optimal → 💡 switch suggestion (better model is configured)
 * sidenotes only → 💡 sidenote (current is best configured, but better exists unconfigured)
 * current_is_optimal && no sidenotes → silent (don't add noise)
 *
 * @param {object} rec
 * @param {string} currentModelId
 */
function _renderRecommendation(rec, currentModelId) {
 if (!rec) return;

 // Task cannot be completed with any configured model
 if (rec.cannot_complete) {
 const missing = rec.sidenotes.map(s => s.display).join(' or ');
 _appendRecommendationChip(
 `⛔ <strong>${rec.task_label}</strong> requires a multimodal model (${missing || 'not configured'}). ` +
 `Add it in <strong>⚙ API Keys</strong> to complete this task.`,
 'error',
 );
 return;
 }

 // Better configured model available — suggest a switch
 if (!rec.current_is_optimal && rec.recommended_model_id && rec.recommended_model_id !== currentModelId) {
 let msg =
 `💡 <strong>${rec.task_label}</strong> — ` +
 `<strong>${rec.recommended_model_display}</strong> is a better fit than your current model. ` +
 `Switch in the model dropdown above.`;

 if (rec.sidenotes && rec.sidenotes.length > 0) {
 msg += ` <em>(${rec.sidenotes[0].display} would be even better — ${rec.sidenotes[0].reason})</em>`;
 }
 if (rec.profile_note) {
 msg += ` ${rec.profile_note}`;
 }
 _appendRecommendationChip(msg, 'tip');
 return;
 }

 // Current model is optimal but superior unconfigured models exist → sidenote
 if (rec.sidenotes && rec.sidenotes.length > 0) {
 const s = rec.sidenotes[0];
 let msg =
 `💡 <em>Side note:</em> <strong>${s.display}</strong> would handle ` +
 `<strong>${rec.task_label}</strong> even better — ${s.reason}.`;
 if (rec.profile_note) {
 msg += ` ${rec.profile_note}`;
 }
 _appendRecommendationChip(msg, 'sidenote');
 return;
 }

 // Profile note with no other recommendation (e.g. privacy mode)
 if (rec.profile_note) {
 _appendRecommendationChip(`💡 ${rec.profile_note}`, 'sidenote');
 }

 // current_is_optimal with no sidenotes → stay silent
}

/**
 * Inject a styled recommendation chip into the chat message list.
 *
 * @param {string} html — inner HTML (may include <strong>/<em>)
 * @param {'tip'|'sidenote'|'error'} variant
 */
function _appendRecommendationChip(html, variant = 'tip') {
 const el = document.createElement('div');
 el.className = `chat-recommendation chat-recommendation--${variant}`;
 el.innerHTML = html;
 _msgContainer().appendChild(el);
 _scrollBottom();
}

/**
 * Keydown handler for the chat textarea.
 * Enter → send. Shift+Enter → newline.
 */
export function chatKeydown(event) {
 if (event.key === 'Enter' && !event.shiftKey) {
 event.preventDefault();
 sendChatMessage();
 }
}

// ── Message rendering ─────────────────────────────────────────────────────────

function _appendUserBubble(text) {
 const el = document.createElement('div');
 el.className = 'chat-bubble chat-bubble-user';
 el.textContent = text;
 _msgContainer().appendChild(el);
 _scrollBottom();
}

function _appendAIBubble() {
 const wrapperEl = document.createElement('div');
 wrapperEl.className = 'chat-bubble chat-bubble-ai';

 const contentEl = document.createElement('span');
 contentEl.className = 'chat-bubble-content';

 const cursorEl = document.createElement('span');
 cursorEl.className = 'chat-cursor';
 cursorEl.textContent = '▋';

 wrapperEl.appendChild(contentEl);
 wrapperEl.appendChild(cursorEl);
 _msgContainer().appendChild(wrapperEl);
 _scrollBottom();

 return { wrapperEl, contentEl, cursorEl };
}

function _appendSystemMessage(text) {
 const el = document.createElement('div');
 el.className = 'chat-system-msg';
 el.textContent = text;
 _msgContainer().appendChild(el);
 _scrollBottom();
}

function _msgContainer() {
 return document.getElementById('chat-messages');
}

function _scrollBottom() {
 const el = _msgContainer();
 if (el) el.scrollTop = el.scrollHeight;
}

// ── Internal helpers ──────────────────────────────────────────────────────────

function _resetState() {
 _sessionId = null;
 _apiBase = null;
 _authHeaders = {};
 _history = [];
 _streaming = false;
 _models = [];

 const msgs = document.getElementById('chat-messages');
 if (msgs) msgs.innerHTML = '';

 const input = document.getElementById('chat-input');
 if (input) input.value = '';

 const select = document.getElementById('model-select');
 if (select) select.innerHTML = '<option>—</option>';

 const sendBtn = document.getElementById('btn-send-chat');
 if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = 'Send'; }
}
