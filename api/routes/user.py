"""
api/routes/user.py — User provisioning endpoints.

Provisions a new sovereign AI vault for a user:
/user/provision/start → mint context token → return token_id + challenge
/user/provision/complete → wallet sig → derive keys → push vault → register in contract
/user/{token_id}/status → check if vault is registered

Two-step design:
1. Start mints the context token on-chain (operator pays, can't be undone).
   Returns token_id + challenge_hex.
2. User's wallet signs challenge_hex (same as /session/open challenge for this token_id).
3. Complete derives encryption keys from that sig, creates default vault content,
   pushes all sections to HFS, registers the vault index in the contract.
4. User can immediately call /session/open with the same wallet_signature_hex.

The wallet signature that encrypts the vault is the SAME signature that decrypts it
at session open — no separate credential store, no key escrow. The user's wallet IS the key.
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.crypto import make_challenge, derive_key, compress
from src.context_token import mint_context_token
from src.vault import (
    push_section,
    push_index,
    get_registered_file_id as _get_registered_file_id,
    token_id_to_evm_address,
    get_validator_contract_id,
    _make_section_aad,
    _make_index_aad,
)
from src.contract import register_file
from src.event_log import log_event

from api.models import (
    ProvisionStartRequest,
    ProvisionStartResponse,
    ProvisionCompleteRequest,
    ProvisionCompleteResponse,
    UserStatusResponse,
)
from api.provision_store import create_pending, get_pending, complete_pending

# HKDF info labels — must match vault.py and session.py
_INFO_SECTION = b"sovereign-ai-section-v1"
_INFO_INDEX = b"sovereign-ai-index-v1"

# Identity section names to create at provision time
_PROVISION_SECTIONS = ["harness", "user", "config", "session_state"]

router = APIRouter(prefix="/user", tags=["user"])


# ---------------------------------------------------------------------------
# Default vault content templates
# ---------------------------------------------------------------------------

def _default_sections(token_id: str, account_id: str, companion_name: str, created_at: str) -> dict[str, bytes]:
    """
    Generate default vault content for a newly provisioned user.
    These are starting templates — the user customizes them post-provision.
    """
    return {
        "harness": f"""# Harness Directives

**Token:** {token_id}
**Account:** {account_id}
**Created:** {created_at}

This is the core of your AI harness — the directives and principles that define
how your AI operates. Customize it to set your AI's mission, values, and ground rules.
You're in command. This is how you tell AI who it's working for and what matters.

[Status: NEW — awaiting customization]
""".encode("utf-8"),

        "user": f"""# User Profile

**Account:** {account_id}
**Token:** {token_id}
**Created:** {created_at}

This is your profile — context your AI carries into every session.
Add your preferences, communication style, background, and goals.
The more you put in, the better AI understands how to serve you.

[Status: NEW — awaiting customization]
""".encode("utf-8"),

        "config": f"""# AI Configuration

**Name:** {companion_name}
**Token:** {token_id}
**Created:** {created_at}

This defines how your AI thinks, speaks, and responds.
Customize it to set the tone, expertise, and working style you want.
You built this harness — your AI follows it.

[Status: NEW — awaiting customization]
""".encode("utf-8"),

        "session_state": f"""# Session State

**Last Updated:** {created_at}
**Token:** {token_id}
**Status:** NEW

Updated after each session. Tracks what was worked on and what comes next —
so your AI picks up exactly where you left off.

[Status: NEW — no sessions yet]
""".encode("utf-8"),
    }


# ---------------------------------------------------------------------------
# /user/provision/start
# ---------------------------------------------------------------------------

@router.post("/provision/start", response_model=ProvisionStartResponse)
def provision_start(req: ProvisionStartRequest) -> ProvisionStartResponse:
    """
    Step 1 of user provisioning. Mints a context token and returns the challenge to sign.

    The operator pays the token creation gas (HBAR). This is a billable action —
    implement a payment/subscription gate here before production use.

    Returns token_id and challenge_hex. The user must:
    1. Sign challenge_hex with their wallet
    2. Call /user/provision/complete with the token_id and wallet_signature_hex

    The signed challenge is the same as the /session/open challenge — once provisioning
    is complete, the same wallet_signature_hex opens the first session immediately.
    """
    account_id = req.account_id.strip()

    # Mint the context token (placeholder context_file_id — updated after vault creation)
    try:
        token_id = mint_context_token(
            context_file_id="pending",
            companion_name=req.companion_name,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Context token mint failed: {exc}")

    # Register pending record
    pending = create_pending(
        token_id=token_id,
        account_id=account_id,
        companion_name=req.companion_name,
    )

    challenge = make_challenge(token_id)

    return ProvisionStartResponse(
        token_id=token_id,
        challenge_hex=challenge.hex(),
        expires_at=pending.expires_iso,
    )


# ---------------------------------------------------------------------------
# /user/provision/complete
# ---------------------------------------------------------------------------

@router.post("/provision/complete", response_model=ProvisionCompleteResponse)
def provision_complete(req: ProvisionCompleteRequest) -> ProvisionCompleteResponse:
    """
    Step 2 of user provisioning. Creates the encrypted vault and registers it on-chain.

    Flow:
    1. Verify token_id has a pending provision record (started via /provision/start)
    2. Parse wallet_signature_hex
    3. Derive section_key + index_key from (token_id, wallet_sig) — Claim 14
    4. Create default vault content (customizable post-provision)
    5. Compress + encrypt + push each section to HFS
    6. Build vault index JSON → encrypt + push to HFS
    7. Register index file_id in ContextValidator contract
    8. Log VAULT_PROVISIONED to HCS
    9. Return confirmation

    After this call:
    - /session/open accepts the same wallet_signature_hex immediately
    - The vault is encrypted — only the holder of the wallet can decrypt it
    """
    token_id = req.token_id

    # ---- Verify pending record ----
    pending = get_pending(token_id)
    if not pending:
        raise HTTPException(
            status_code=404,
            detail=f"No pending provision for token '{token_id}'. "
            "Call /provision/start first, or the 60-minute window has expired.",
        )

    # ---- Derive IKM from passphrase (SHA-256 hash, never stored) ----
    if not req.passphrase or len(req.passphrase) < 8:
        raise HTTPException(status_code=400, detail="Passphrase must be at least 8 characters.")
    ikm = hashlib.sha256(req.passphrase.encode("utf-8")).digest()

    # ---- Derive purpose-separated keys (Claim 14 + Element H) ----
    section_key = derive_key(token_id, ikm, info=_INFO_SECTION)
    index_key = derive_key(token_id, ikm, info=_INFO_INDEX)

    # ---- Verify contract is configured ----
    contract_id = get_validator_contract_id()
    if not contract_id:
        raise HTTPException(
            status_code=503,
            detail="VALIDATOR_CONTRACT_ID not configured — cannot register vault.",
        )

    # ---- Create default vault content ----
    created_at = datetime.now(timezone.utc).isoformat()
    default_sections = _default_sections(
        token_id=token_id,
        account_id=pending.account_id,
        companion_name=pending.companion_name,
        created_at=created_at,
    )

    # ---- Push each section to HFS ----
    section_file_ids: dict[str, str] = {}
    try:
        for section_name, content in default_sections.items():
            file_id = push_section(
                section_name=section_name,
                content=content,
                key=section_key,
                token_id=token_id,
                existing_file_id=None,
            )
            section_file_ids[section_name] = file_id
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HFS section push failed: {exc}")

    # ---- Push vault index to HFS (with content hashes for tamper detection) ----
    # Hash each section's plaintext — verified on every session open (Content Hash Index sub-claim).
    section_content_hashes = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in default_sections.items()
        if name in section_file_ids
    }
    try:
        index_file_id = push_index(
            section_file_ids,
            index_key,
            token_id,
            section_hashes=section_content_hashes,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HFS index push failed: {exc}")

    # ---- Register vault index in ContextValidator contract ----
    try:
        token_evm = token_id_to_evm_address(token_id)
        register_file(contract_id, token_evm, serial=1, file_id=index_file_id)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Vault HFS push succeeded but contract registration failed: {exc}. "
            f"Token minted and vault exists on HFS — contact support with token_id={token_id}.",
        )

    # ---- Log to HCS ----
    try:
        log_event(
            event_type="VAULT_PROVISIONED",
            payload={
                "token_id": token_id,
                "account_id": pending.account_id,
                "companion_name": pending.companion_name,
                "sections": list(section_file_ids.keys()),
                "index_file_id": index_file_id,
                "vault_registered": True,
                "created_at": created_at,
            },
        )
    except Exception:
        pass  # Non-fatal

    # ---- Clear pending record ----
    complete_pending(token_id)

    return ProvisionCompleteResponse(
        token_id=token_id,
        sections_pushed=list(section_file_ids.keys()),
        index_file_id=index_file_id,
        vault_registered=True,
        message=(
            "Vault provisioned successfully. "
            "Call POST /session/open with your token_id and wallet_signature_hex to start your first session."
        ),
    )


# ---------------------------------------------------------------------------
# /user/{token_id}/status
# ---------------------------------------------------------------------------

@router.get("/{token_id}/status", response_model=UserStatusResponse)
def user_status(token_id: str) -> UserStatusResponse:
    """
    Check whether a vault is registered for the given context token.

    Returns the index_file_id if registered. Does NOT return vault contents —
    those require a valid wallet signature to decrypt.
    """
    contract_id = get_validator_contract_id()
    if not contract_id:
        raise HTTPException(status_code=503, detail="VALIDATOR_CONTRACT_ID not configured.")

    try:
        token_evm = token_id_to_evm_address(token_id)
        index_file_id = _get_registered_file_id(contract_id, token_evm, serial=1)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Contract query failed: {exc}")

    if index_file_id:
        return UserStatusResponse(
            token_id=token_id,
            registered=True,
            index_file_id=index_file_id,
            message="Vault is registered. Use POST /session/open to access it.",
        )
    return UserStatusResponse(
        token_id=token_id,
        registered=False,
        index_file_id=None,
        message="No vault registered for this token. Run /provision/complete first.",
    )
