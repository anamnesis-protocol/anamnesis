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
_PROVISION_SECTIONS = ["harness", "user", "config", "session_state", "system", "credentials"]

router = APIRouter(prefix="/user", tags=["user"])


# ---------------------------------------------------------------------------
# Default vault content templates
# ---------------------------------------------------------------------------

def _system_section_content(token_id: str, created_at: str) -> bytes:
    """
    Generate the system capabilities section for a vault.

    Describes the vault architecture, RAG index, MCP server, skill packages, and
    health check tools so the AI companion understands what it has access to.
    Injected as part of the system prompt at every session open.
    """
    return f"""# System Capabilities

**Token:** {token_id}
**Initialized:** {created_at}

This companion runs within the Arty Fitchels sovereign AI context system.
Context is stored encrypted on Hedera Hashgraph — only your wallet signature can decrypt it.
Nothing unencrypted ever touches a server at rest or in transit beyond your active session.

## Vault Sections
Five sections are loaded into every session:
- **harness** — your AI's core directives, mission, and operating principles
- **user** — your profile, preferences, background, and goals
- **config** — AI name, tone, style, and response configuration
- **session_state** — auto-updated after every session to carry forward what was worked on
- **system** — this section (platform capabilities — reference only)

Each section is stored as AES-GCM ciphertext on Hedera File Service (HFS).
Keys are derived fresh from your wallet signature on every session open using HKDF-SHA256, then zeroed on close.
The vault index (section → HFS file_id mapping) is also encrypted on HFS and resolved via the ContextValidator contract.

## Context Retrieval (RAG)
Vault content is indexed with BM25 at session open.
Relevant context chunks are retrieved automatically on each conversation turn and injected
alongside your message — you do not need to supply background manually.
The index is rebuilt in-memory on every session open from the decrypted vault sections.
Check retrieval quality: GET /vault/health → rag_index check

## Skill Packages
Skill packages are MCP tool definitions stored encrypted in your vault.
When the AI learns a reusable task, it can be packaged as a skill and stored permanently.
Skills load automatically at session open and become available as callable tools in any future
session with any AI model — no re-teaching required.
Manage skills: GET /skills | POST /skills | DELETE /skills/{{skill_id}}
Skills as MCP tools: GET /skills/tools

## MCP Server
Your vault exposes a Model Context Protocol server that any MCP-compatible AI client can connect to.

Static tools available in every session:
- open_session — decrypt vault from Hedera, return session_id
- close_session — sync changed sections to Hedera, zero session keys
- get_vault_section — read any vault section by name
- update_vault_section — queue a section update to be synced at close
- list_skills — list all skill packages in this vault
- save_skill_to_vault — package a learned task as a permanent vault skill

Dynamic tools: each skill package stored in your vault is registered as a live MCP tool at session open.
Run the MCP server: python -m api.mcp_server --transport stdio

## Vault Health and Auto-Repair
Check your vault state against your live decrypted content at any time (requires active session):
- GET /vault/health?session_id=<id> — completeness, RAG quality, staleness, structure, HFS registry, duplicates
- POST /vault/health/repair?session_id=<id> — rebuilds RAG index, applies all auto-fixes
- POST /vault/upgrade?session_id=<id> — adds missing system capabilities section (this file)

Health report: overall status (healthy / degraded / critical) with per-check breakdowns and actionable notes.

## Session Lifecycle
Sessions are valid for 4 hours. Concurrent sessions for the same token are blocked (409 Conflict) to
prevent key collision. At close, changed sections are diffed against session-open hashes — only
changed content is re-encrypted and pushed to Hedera. If a chat happened and session_state was not
manually updated, a brief summary is auto-generated and written back to the vault.
""".encode("utf-8")


def _create_hedera_account() -> tuple[str, str]:
    """
    Create a new Hedera account sponsored by the operator.
    Returns (account_id_str, private_key_str).
    Operator pays the ~$0.05 HBAR account creation fee.
    """
    from hiero_sdk_python import AccountCreateTransaction, PrivateKey, Hbar
    from hiero_sdk_python.hapi.services import response_code_pb2 as _rc
    _SUCCESS_CODE = _rc.SUCCESS

    from src.config import get_client, get_treasury
    client = get_client()
    _, treasury_key = get_treasury()

    new_key = PrivateKey.generate("ed25519")

    tx = (
        AccountCreateTransaction()
        .set_key(new_key.public_key())
        .set_initial_balance(Hbar(0))
        .freeze_with(client)
        .sign(treasury_key)
    )

    receipt = tx.execute(client)
    if receipt.status != _SUCCESS_CODE:
        raise RuntimeError(f"AccountCreateTransaction failed: status={receipt.status}")

    if receipt.account_id is None:
        raise RuntimeError("AccountCreateTransaction succeeded but receipt has no account_id")

    return str(receipt.account_id), new_key.to_string()


def _default_sections(
    token_id: str,
    account_id: str,
    companion_name: str,
    created_at: str,
    private_key_hex: str | None = None,
) -> dict[str, bytes]:
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

        "system": _system_section_content(token_id, created_at),

        "credentials": (
            f"""# Hedera Credentials

**Account:** {account_id}
**Token:** {token_id}
**Created:** {created_at}

## Private Key
{private_key_hex}

## Important
This is your Hedera account private key — store it somewhere safe outside this vault.
It controls your Hedera account ({account_id}).
Your vault encryption is separate and protected by your passphrase.
"""
            if private_key_hex else
            f"""# Hedera Credentials

**Account:** {account_id}
**Token:** {token_id}
**Created:** {created_at}

You connected your own Hedera account. Your private key is managed by your wallet.
"""
        ).encode("utf-8"),
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
    # Auto-create a Hedera account if the user didn't provide one
    generated_private_key_hex: str | None = None
    if req.account_id:
        account_id = req.account_id.strip()
    else:
        try:
            account_id, generated_private_key_hex = _create_hedera_account()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Hedera account creation failed: {exc}")

    # Mint the context token (placeholder context_file_id — updated after vault creation)
    try:
        token_id = mint_context_token(
            context_file_id="pending",
            companion_name=req.companion_name,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Context token mint failed: {exc}")

    # Register pending record (private key stored here until vault is created)
    pending = create_pending(
        token_id=token_id,
        account_id=account_id,
        companion_name=req.companion_name,
        generated_private_key_hex=generated_private_key_hex,
    )

    challenge = make_challenge(token_id)

    return ProvisionStartResponse(
        token_id=token_id,
        account_id=account_id,
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
        private_key_hex=pending.generated_private_key_hex,
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
