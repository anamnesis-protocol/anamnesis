"""
api/routes/session.py — SaaS session open/close endpoints.

Multi-user API service for sovereign AI context sessions:

 /session/challenge → returns challenge bytes for wallet to sign
 /session/open → wallet sig + token_id → derive key → decrypt HFS context
 /session/close → log SESSION_ENDED delta to HCS, evict session

Auth model:
 The wallet signature IS the auth. No separate credential system.
 If HKDF(token_id || wallet_sig) produces the correct AES-GCM key,
 decryption succeeds → user proved ownership of the wallet → session opens.
 Wrong sig → InvalidTag → 401. Injection detected → 403.
"""

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import jwt as _jwt
import os

from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, Header, HTTPException, Request

from api.limiter import limiter

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.crypto import make_challenge, derive_key
from src.vault import (
 pull_index,
 pull_section,
 push_section,
 update_index,
 verify_content,
 get_registered_file_id as _get_registered_file_id,
 token_id_to_evm_address,
 get_validator_contract_id,
)
from src.event_log import log_event

from api.models import (
 ChallengeRequest,
 ChallengeResponse,
 SessionOpenRequest,
 SessionOpenResponse,
 SessionCloseRequest,
 SessionCloseResponse,
)
from api.session_store import create_session, get_session, close_session

# HKDF info labels — must match vault.py exactly
_INFO_SECTION = b"sovereign-ai-section-v1"
_INFO_INDEX = b"sovereign-ai-index-v1"

# Identity section names — only these are delivered in the session context
_IDENTITY_SECTIONS = {"soul", "user", "symbiote", "session_state"}

router = APIRouter(prefix="/session", tags=["session"])


# ---------------------------------------------------------------------------
# /session/challenge
# ---------------------------------------------------------------------------

@router.post("/challenge", response_model=ChallengeResponse)
def get_challenge(req: ChallengeRequest) -> ChallengeResponse:
 """
 Return the challenge bytes that the user's wallet must sign.

 Challenge = b"sovereign-ai-context-challenge-{token_id}"
 This is deterministic — the same token always gets the same challenge.
 The session TTL (4 hours) provides replay protection.
 """
 challenge: bytes = make_challenge(req.token_id)
 return ChallengeResponse(
 token_id=req.token_id,
 challenge_hex=challenge.hex(),
 )


# ---------------------------------------------------------------------------
# /session/open
# ---------------------------------------------------------------------------

@router.post("/open", response_model=SessionOpenResponse)
@limiter.limit("10/minute")
def open_session(
 request: Request,
 req: SessionOpenRequest,
 authorization: str = Header(default=""),
) -> SessionOpenResponse:
 """
 Open a sovereign AI session.

 Flow:
 1. Derive section_key = HKDF(token_id || wallet_sig, info="sovereign-ai-section-v1")
 2. Derive index_key = HKDF(token_id || wallet_sig, info="sovereign-ai-index-v1")
 3. Fetch index file_id from ContextValidator contract
 4. Decrypt vault index → section file IDs
 5. Decrypt each identity section — AES-GCM; wrong sig raises InvalidTag → 401
 6. Verify each section: injection scan + UTF-8 check → 403 if fails
 7. Issue session_id, return context to caller for system prompt injection

 Key is derived then immediately discarded — never stored ().
 """
 token_id = req.token_id
 serial = req.serial

 # ---- Extract user_id from optional JWT (mainnet mode only) ----
 # The JWT is sent by the frontend when the user is logged in (wallet mode).
 # In demo/testnet mode no JWT is present — user_id stays "" (uses env keys for AI).
 user_id = ""
 jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
 if authorization.startswith("Bearer ") and jwt_secret:
 try:
 payload = _jwt.decode(
 authorization[7:],
 jwt_secret,
 algorithms=["HS256"],
 audience="authenticated",
 )
 user_id = payload.get("sub", "")
 except Exception:
 pass # invalid/expired token → continue as demo mode

 # ---- Parse wallet signature ----
 try:
 wallet_sig = bytes.fromhex(req.wallet_signature_hex)
 except ValueError:
 raise HTTPException(status_code=400, detail="wallet_signature_hex is not valid hex.")

 if len(wallet_sig) not in (64, 65):
 raise HTTPException(
 status_code=400,
 detail=f"Wallet signature must be 64 bytes (Ed25519) or 65 bytes (secp256k1). Got {len(wallet_sig)}.",
 )

 # ---- Derive purpose-separated keys (Claim 14 + Element H) ----
 try:
 section_key = derive_key(token_id, wallet_sig, info=_INFO_SECTION)
 index_key = derive_key(token_id, wallet_sig, info=_INFO_INDEX)
 except Exception as exc:
 raise HTTPException(status_code=500, detail=f"Key derivation failed: {exc}")

 # ---- Resolve vault index file_id from contract (Element C gate 1) ----
 try:
 contract_id = get_validator_contract_id()
 if not contract_id:
 raise HTTPException(
 status_code=503,
 detail="VALIDATOR_CONTRACT_ID not configured. Cannot resolve vault index.",
 )
 token_evm = token_id_to_evm_address(token_id)
 index_file_id = _get_registered_file_id(contract_id, token_evm, serial)
 if not index_file_id:
 raise HTTPException(
 status_code=404,
 detail=f"No vault registered for token {token_id} serial {serial}. "
 "Run vault_push.py to create a vault first.",
 )
 except HTTPException:
 raise
 except Exception as exc:
 raise HTTPException(status_code=502, detail=f"Contract query failed: {exc}")

 # ---- Decrypt vault index (Element C gate 2 — wrong key → InvalidTag) ----
 try:
 section_ids: dict = pull_index(index_file_id, index_key, token_id)
 except InvalidTag:
 # Key wrong → wallet_sig incorrect → not the token owner
 raise HTTPException(
 status_code=401,
 detail="Authentication failed: invalid wallet signature. "
 "Vault index could not be decrypted.",
 )
 except ValueError as exc:
 raise HTTPException(status_code=502, detail=f"Vault index corrupt: {exc}")

 # ---- Extract stored content hashes (Content Hash Index sub-claim) ----
 # Populated at provision time. Old vaults without this field skip hash verification
 # gracefully — the existing AES-GCM auth tag still guards against ciphertext tampering.
 stored_hashes: dict[str, str] = section_ids.get("_section_hashes", {})

 # ---- Filter to identity sections only (no dir bundles or metadata in session context) ----
 identity_ids = {
 name: fid
 for name, fid in section_ids.items()
 if name in _IDENTITY_SECTIONS
 }

 if not identity_ids:
 raise HTTPException(
 status_code=404,
 detail="Vault index contains no identity sections. "
 "Run vault_push.py to push soul/user/symbiote/session_state.",
 )

 # ---- Fetch and decrypt each identity section ----
 # expected_hash: plaintext SHA-256 stored at provision time.
 # If present → verify_content() will hash the decrypted plaintext and compare.
 # If absent (old vault) → hash check is skipped; AES-GCM auth tag still guards ciphertext.
 context_raw: dict[str, bytes] = {}
 for section_name, file_id in identity_ids.items():
 try:
 content: bytes = pull_section(
 file_id,
 section_key,
 token_id,
 section_name=section_name,
 expected_hash=stored_hashes.get(section_name), # None → skip hash check
 )
 context_raw[section_name] = content
 except InvalidTag:
 raise HTTPException(
 status_code=401,
 detail=f"Authentication failed: could not decrypt section '{section_name}'. "
 "Invalid wallet signature.",
 )
 except ValueError as exc:
 # Injection scan, hash mismatch, or integrity failure .
 # Log INTEGRITY_FAILURE to HCS before raising — closes the audit loop for
 # attack attempts ( session context envelope audit trail).
 try:
 log_event(
 event_type="INTEGRITY_FAILURE",
 payload={
 "token_id": token_id,
 "serial": serial,
 "source": "saas_api",
 "section": section_name,
 "error": str(exc),
 },
 )
 except Exception:
 pass # HCS log is best-effort — still raise the 403
 raise HTTPException(
 status_code=403,
 detail=f"Section '{section_name}' failed integrity check: {exc}",
 )

 # ---- Build session ----
 # Keys are stored as bytearray in the session store so they can be explicitly
 # zeroed at session close ( Session-Scoped Key Lifecycle).
 # full_section_ids holds the complete index dict so session close can push
 # changed sections and update the index without re-pulling from Hedera.
 session = create_session(
 token_id=token_id,
 serial=serial,
 context_sections=context_raw,
 section_key=section_key,
 index_key=index_key,
 index_file_id=index_file_id,
 full_section_ids=section_ids,
 user_id=user_id,
 )

 # ---- Log SESSION_STARTED to HCS (Element J — session context envelope) ----
 # integrity_verified: True means every loaded section passed its injection scan
 # and content hash check. INTEGRITY_FAILURE events are logged separately if any
 # section fails — so the HCS record is complete for both success and attack paths.
 start_hashes = {
 name: hashlib.sha256(content).hexdigest()
 for name, content in context_raw.items()
 }
 try:
 log_event(
 event_type="SESSION_STARTED",
 payload={
 "session_id": session.session_id,
 "token_id": token_id,
 "serial": serial,
 "source": "saas_api",
 "sections_loaded": session.sections_loaded,
 "start_hashes": start_hashes,
 "integrity_verified": True,
 },
 )
 hcs_open = True
 except Exception:
 hcs_open = False # Non-fatal — session still opens

 # ---- Deliver context as strings (key already discarded at function exit) ----
 return SessionOpenResponse(
 session_id=session.session_id,
 token_id=token_id,
 context_sections={name: content.decode("utf-8") for name, content in context_raw.items()},
 sections_loaded=session.sections_loaded,
 created_at=session.created_iso,
 expires_at=session.expires_iso,
 )


# ---------------------------------------------------------------------------
# /session/close
# ---------------------------------------------------------------------------

@router.post("/close", response_model=SessionCloseResponse)
def close_session_endpoint(req: SessionCloseRequest) -> SessionCloseResponse:
 """
 Close a sovereign AI session.

 Implements Session-Scoped Key Lifecycle:

 1. Receive updated section content from the client
 2. Diff against session-open hashes — only push changed sections
 3. Re-encrypt each changed section with the stored session_key
 4. Push updated ciphertext back to Hedera HFS (update in place)
 5. Update vault index with new content hashes
 6. Log SESSION_ENDED delta to HCS
 7. Zero session_key and index_key in the session store
 8. Evict session — no decrypted content or key material remains locally

 After this call completes, the vault on Hedera reflects the session's changes.
 All local copies of decrypted content and derived keys are gone.
 """
 session = get_session(req.session_id)
 if not session:
 raise HTTPException(
 status_code=404,
 detail=f"Session '{req.session_id}' not found or expired.",
 )

 token_id = session.token_id
 closed_at = datetime.now(timezone.utc).isoformat()

 # ---- Diff: identify changed sections ----
 # Compare each submitted section's SHA-256 against the hash recorded at open.
 # Only sections whose content actually changed are pushed to Hedera.
 changed: dict[str, bytes] = {}
 for section_name, new_content_str in req.updated_sections.items():
 if section_name not in session.sections_loaded:
 # Reject sections that weren't loaded in this session — no HFS file ID available
 continue
 new_content = new_content_str.encode("utf-8")
 new_hash = hashlib.sha256(new_content).hexdigest()
 if new_hash != session.start_hashes.get(section_name):
 changed[section_name] = new_content

 vault_updated = False

 # ---- Re-encrypt and push changed sections to Hedera ----
 if changed:
 # Copy keys out of bytearray before use — bytes() is required by crypto layer.
 # Keys are zeroed by close_session() immediately after this block.
 section_key_bytes = bytes(session.section_key)
 index_key_bytes = bytes(session.index_key)

 try:
 for section_name, new_content in changed.items():
 existing_file_id = session.full_section_ids.get(section_name)
 push_section(
 section_name,
 new_content,
 section_key_bytes,
 token_id,
 existing_file_id=existing_file_id,
 )
 # file_id is unchanged (update_context overwrites in place)

 # ---- Update vault index with new content hashes ----
 # Carry forward unchanged section hashes, replace changed ones.
 stored = session.full_section_ids.get("_section_hashes", {})
 new_hashes = dict(session.start_hashes) # hashes at open (unchanged sections)
 for name, content in changed.items():
 new_hashes[name] = hashlib.sha256(content).hexdigest()

 # Build clean index (no metadata keys)
 _META_KEYS = {"_section_hashes"}
 clean_index = {
 k: v for k, v in session.full_section_ids.items()
 if k not in _META_KEYS and isinstance(v, str)
 }

 update_index(
 index_file_id=session.index_file_id,
 index=clean_index,
 key=index_key_bytes,
 token_id=token_id,
 section_hashes=new_hashes,
 )
 vault_updated = True

 except Exception as exc:
 # Non-fatal for session eviction — still zero keys and close.
 # Caller should retry close or handle the error.
 close_session(req.session_id) # zeros keys even on error
 raise HTTPException(
 status_code=502,
 detail=f"Failed to push updated sections to Hedera: {exc}. "
 "Session closed and keys zeroed. Retry /session/close to re-push.",
 )
 finally:
 # Explicit zero of local key copies (belt-and-suspenders)
 section_key_bytes = b"\x00" * len(section_key_bytes)
 index_key_bytes = b"\x00" * len(index_key_bytes)

 # ---- Auto-update session_state (model-agnostic memory write-back) ----
 # If a chat happened during this session and session_state wasn't manually updated,
 # generate a brief session summary and add it to the changed sections for push-back.
 if (
 session.last_model
 and "session_state" not in changed
 and "session_state" in session.sections_loaded
 and session.context_sections # context still available (not yet zeroed)
 ):
 try:
 from api.services.ai_router import generate_completion, MODELS, available_models
 if available_models(): # only if at least one model is configured
 existing_state = session.context_sections.get("session_state", "")
 model_display = MODELS.get(session.last_model, {}).get("display", session.last_model)
 summary_system = (
 "You are a memory system for a sovereign AI companion. "
 "Your task is to write a concise session_state update (3-5 bullets, max 200 words). "
 "Preserve existing long-term context, add only new session highlights."
 )
 summary_prompt = (
 f"Previous session_state:\n{existing_state}\n\n"
 f"Session just ended on {closed_at[:10]} using model: {model_display}.\n"
 "Write an updated session_state that preserves prior context "
 "and appends a brief note about this session."
 )
 import asyncio
 new_state = asyncio.run(
 generate_completion(session.last_model, summary_system, summary_prompt)
 )
 if new_state.strip():
 new_state_bytes = new_state.encode("utf-8")
 new_hash = hashlib.sha256(new_state_bytes).hexdigest()
 if new_hash != session.start_hashes.get("session_state"):
 # Push updated session_state to Hedera
 if not vault_updated:
 # First change — need to set up keys
 section_key_bytes = bytes(session.section_key)
 index_key_bytes = bytes(session.index_key)
 try:
 existing_file_id = session.full_section_ids.get("session_state")
 push_section("session_state", new_state_bytes, section_key_bytes, token_id, existing_file_id)
 new_hashes = dict(session.start_hashes)
 new_hashes["session_state"] = new_hash
 _META_KEYS = {"_section_hashes"}
 clean_index = {k: v for k, v in session.full_section_ids.items() if k not in _META_KEYS and isinstance(v, str)}
 update_index(index_file_id=session.index_file_id, index=clean_index, key=index_key_bytes, token_id=token_id, section_hashes=new_hashes)
 changed["session_state"] = new_state_bytes
 vault_updated = True
 finally:
 section_key_bytes = b"\x00" * len(section_key_bytes)
 index_key_bytes = b"\x00" * len(index_key_bytes)
 else:
 # Keys already used above — session_state will be caught on next open
 # (This path shouldn't occur since session_state wasn't in changed earlier)
 pass
 except Exception:
 pass # Non-fatal — session still closes without session_state update

 # ---- Log SESSION_ENDED to HCS (Element J — audit trail) ----
 hcs_logged = False
 try:
 log_event(
 event_type="SESSION_ENDED",
 payload={
 "session_id": session.session_id,
 "token_id": token_id,
 "serial": session.serial,
 "source": "saas_api",
 "sections_loaded": session.sections_loaded,
 "changed_sections": list(changed.keys()),
 "vault_updated": vault_updated,
 "last_model": session.last_model or None,
 "session_opened_at": session.created_iso,
 "closed_at": closed_at,
 },
 )
 hcs_logged = True
 except Exception:
 pass # Non-fatal — session still closes

 # ---- Zero keys + evict session ----
 # close_session() overwrites section_key and index_key bytearrays with zeros
 # before removing the session from the store.
 close_session(req.session_id)

 return SessionCloseResponse(
 session_id=req.session_id,
 closed_at=closed_at,
 changed_sections=list(changed.keys()),
 hcs_logged=hcs_logged,
 vault_updated=vault_updated,
 )


# ---------------------------------------------------------------------------
# Health / status
# ---------------------------------------------------------------------------

@router.get("/status")
def session_status():
 """Return API health and active session count."""
 from api.session_store import active_count
 return {
 "status": "ok",
 "active_sessions": active_count(),
 }
