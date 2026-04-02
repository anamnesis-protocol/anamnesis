/**
 * vault-context.js — Sovereign AI Context session lifecycle
 *
 * Generic context layer for any user's vault. All context is loaded
 * and saved via the session API — no local file paths, no hardcoded names.
 *
 * Session lifecycle:
 *   1. openSession(apiBase, tokenId, walletSigHex)
 *      → POST /session/open → decrypted vault sections returned
 *   2. Use sections in chat (soul, user, symbiote, session_state)
 *   3. closeSession(apiBase, sessionId, updatedSections)
 *      → POST /session/close → diffs pushed back to HFS
 *
 * Provisioning (first-time users):
 *   1. provisionStart(apiBase, accountId, companionName)
 *      → POST /user/provision/start → token_id + challenge_hex
 *   2. User signs challenge_hex with their wallet
 *   3. provisionComplete(apiBase, tokenId, walletSigHex)
 *      → POST /user/provision/complete → vault created on HFS
 *   4. Then call openSession() — same walletSigHex works immediately
 */

// ---------------------------------------------------------------------------
// Session management
// ---------------------------------------------------------------------------

/**
 * Open a vault session.
 *
 * @param {string} apiBase - Base URL of the API (e.g. "http://localhost:8000")
 * @param {string} tokenId - Hedera context token ID (e.g. "0.0.12345")
 * @param {string} walletSigHex - Hex-encoded wallet signature over the challenge
 * @returns {{ sessionId, tokenId, sections }}
 *   sections = { soul, user, symbiote, session_state } as plain text strings
 */
export async function openSession(apiBase, tokenId, walletSigHex) {
    const response = await fetch(`${apiBase}/session/open`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            token_id: tokenId,
            wallet_signature_hex: walletSigHex,
        }),
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `Session open failed: HTTP ${response.status}`);
    }

    const data = await response.json();
    return {
        sessionId: data.session_id,
        tokenId: data.token_id,
        sections: data.vault_sections || {},
    };
}

/**
 * Close a vault session and push any changed sections back to HFS.
 *
 * Only sections that differ from what was loaded will be pushed
 * (diff-based sync via session_store.get_changed_sections on the backend).
 *
 * @param {string} apiBase
 * @param {string} sessionId - session_id returned by openSession
 * @param {Object} updatedSections - { soul?, user?, symbiote?, session_state? }
 * @returns {{ sections_pushed, hcs_sequence_number }}
 */
export async function closeSession(apiBase, sessionId, updatedSections) {
    const response = await fetch(`${apiBase}/session/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            session_id: sessionId,
            updated_sections: updatedSections,
        }),
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `Session close failed: HTTP ${response.status}`);
    }

    return await response.json();
}

// ---------------------------------------------------------------------------
// Challenge helper (for wallets that need the raw bytes to sign)
// ---------------------------------------------------------------------------

/**
 * Fetch the challenge bytes that the wallet should sign for a given token.
 *
 * @param {string} apiBase
 * @param {string} tokenId
 * @returns {string} challenge_hex
 */
export async function getChallenge(apiBase, tokenId) {
    const response = await fetch(`${apiBase}/session/challenge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token_id: tokenId }),
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `Challenge request failed: HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.challenge_hex;
}

// ---------------------------------------------------------------------------
// Provisioning (first-time vault creation)
// ---------------------------------------------------------------------------

/**
 * Step 1: Start provisioning. Mints a context token on-chain.
 *
 * @param {string} apiBase
 * @param {string} accountId - Hedera account ID of the user (e.g. "0.0.99999")
 * @param {string} companionName - Name for the user's AI companion
 * @returns {{ token_id, challenge_hex, expires_at }}
 */
export async function provisionStart(apiBase, accountId, companionName) {
    const response = await fetch(`${apiBase}/user/provision/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            account_id: accountId,
            companion_name: companionName,
        }),
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `Provision start failed: HTTP ${response.status}`);
    }

    return await response.json();
}

/**
 * Step 2: Complete provisioning. Creates and encrypts the vault on HFS.
 *
 * @param {string} apiBase
 * @param {string} tokenId - token_id from provisionStart
 * @param {string} walletSigHex - wallet signature over challenge_hex from provisionStart
 * @returns {{ token_id, sections_pushed, index_file_id, vault_registered, message }}
 */
export async function provisionComplete(apiBase, tokenId, walletSigHex) {
    const response = await fetch(`${apiBase}/user/provision/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            token_id: tokenId,
            wallet_signature_hex: walletSigHex,
        }),
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `Provision complete failed: HTTP ${response.status}`);
    }

    return await response.json();
}

/**
 * Check whether a vault is registered for a context token.
 *
 * @param {string} apiBase
 * @param {string} tokenId
 * @returns {{ token_id, registered, index_file_id, message }}
 */
export async function getVaultStatus(apiBase, tokenId) {
    const response = await fetch(`${apiBase}/user/${encodeURIComponent(tokenId)}/status`);

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `Status check failed: HTTP ${response.status}`);
    }

    return await response.json();
}

// ---------------------------------------------------------------------------
// Full session flow helpers
// ---------------------------------------------------------------------------

/**
 * Full onboarding flow for a new user.
 *
 * 1. Call provisionStart → get token_id + challenge_hex
 * 2. Call onSignChallenge(challenge_hex) → wallet returns walletSigHex
 * 3. Call provisionComplete → vault created on HFS
 * 4. Call openSession → return session + sections
 *
 * @param {string} apiBase
 * @param {string} accountId
 * @param {string} companionName
 * @param {function} onSignChallenge - async (challenge_hex) => walletSigHex
 * @returns {{ sessionId, tokenId, sections }}
 */
export async function onboardNewUser(apiBase, accountId, companionName, onSignChallenge) {
    const { token_id, challenge_hex } = await provisionStart(apiBase, accountId, companionName);
    const walletSigHex = await onSignChallenge(challenge_hex);
    await provisionComplete(apiBase, token_id, walletSigHex);
    return await openSession(apiBase, token_id, walletSigHex);
}

/**
 * Return session for a returning user (vault already exists).
 *
 * 1. Call getChallenge → challenge_hex
 * 2. Call onSignChallenge(challenge_hex) → wallet returns walletSigHex
 * 3. Call openSession → return session + sections
 *
 * @param {string} apiBase
 * @param {string} tokenId
 * @param {function} onSignChallenge - async (challenge_hex) => walletSigHex
 * @returns {{ sessionId, tokenId, sections }}
 */
export async function resumeSession(apiBase, tokenId, onSignChallenge) {
    const challenge_hex = await getChallenge(apiBase, tokenId);
    const walletSigHex = await onSignChallenge(challenge_hex);
    return await openSession(apiBase, tokenId, walletSigHex);
}
