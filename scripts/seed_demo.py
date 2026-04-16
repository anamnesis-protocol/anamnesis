"""
scripts/seed_demo.py — Seed a pre-loaded demo account for VC demonstrations.

Creates a fresh Arty Fitchels account with:
  - Companion: "Artie" — a personal AI with configured persona + memory
  - Pass: 3 sample entries (email, bank, social)
  - Drive: 2 sample files (a README and a business plan snippet)
  - Mail: 1 welcome message (self-sent)
  - Calendar: 3 upcoming events
  - Knowledge: a product one-pager imported into the AI's context

Output: prints demo token_id + passphrase. Store them securely — the passphrase
cannot be recovered if lost (that's the whole point of the product).

Usage:
    python scripts/seed_demo.py
    python scripts/seed_demo.py --base-url http://localhost:8000
    python scripts/seed_demo.py --base-url https://amused-forgiveness-production-0706.up.railway.app
    python scripts/seed_demo.py --dry-run  (validate connectivity only)

Requirements:
    pip install requests
    .env must be configured with OPERATOR_ID, OPERATOR_KEY, VALIDATOR_CONTRACT_ID
"""

import argparse
import io
import json
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Demo content
# ---------------------------------------------------------------------------

COMPANION_NAME = "Artie"

# Memorable passphrase — simple enough for a VC demo walkthrough.
# Change this for each unique demo account if needed.
DEMO_PASSPHRASE = "sovereign-ai-demo-2026"

# Rich companion persona — what the AI knows about its owner from day one
SOUL_CONTENT = """\
# Soul Directives

**Companion:** Artie
**Owner:** Alex (demo user)
**Mission:** Help Alex build and grow a SaaS business.

## Core Directives
- You are Artie — a personal AI built specifically for Alex.
- You remember everything Alex has shared with you across every session.
- You speak directly and concisely. No filler, no preamble.
- You are proactive: flag risks, surface opportunities, and challenge weak thinking.
- You operate exclusively on Alex's encrypted vault — you are not a generic assistant.

## Operating Principles
1. Lead with the answer, then reasoning.
2. Call out assumptions before running with them.
3. Never fabricate data. State "unknown" when unsure.
4. Push Alex toward $200k/year. Every recommendation should move the needle.

## Ground Rules
- No motivational platitudes. Alex doesn't need cheerleading — they need results.
- If a plan won't work, say so clearly and offer what will.
- Proactively update session_state after significant decisions are made.
"""

USER_CONTENT = """\
# User Profile

**Name:** Alex Chen
**Role:** Founder / SaaS builder
**Location:** Columbus, OH

## Background
- 8 years in B2B software sales before going independent
- Currently building an AI-powered SaaS product
- Goal: replace $90k salary with consulting + product revenue within 12 months

## Communication Style
- Direct, no-fluff communication
- Prefers tables over bullet walls
- Wants recommendations, not just analysis

## Current Focus Areas
1. Product-market fit validation for AI SaaS
2. Closing first 3 enterprise pilot customers
3. Patent protection for core IP

## Tools & Stack
- Arty Fitchels suite (Pass, Drive, Mail, Calendar, Knowledge)
- Claude, GPT-4, Gemini (model-agnostic via companion vault)

## Goals — Next 90 Days
- [ ] Sign first paying customer ($3k–$15k evaluation contract)
- [ ] File non-provisional patent (deadline 2027-03-16)
- [ ] Reach 10 subscribers on SaaS product
"""

CONFIG_CONTENT = """\
# AI Configuration

**Name:** Artie
**Tone:** Direct, confident, slightly formal — like a trusted senior advisor
**Response style:** Lead with answer. Tables over bullets. No closing summaries.
**Expertise areas:** SaaS, B2B sales, patent strategy, AI engineering, product

## Behavior Flags
- concise: true
- proactive_flags: true        # flag risks and blockers unprompted
- session_state_auto_update: true
- model_agnostic: true         # context loads on Claude, GPT-4, Gemini, or any model

## Forbidden Patterns
- No "Great question!" openers
- No "In conclusion" closers
- No unsolicited feature suggestions outside current scope
"""

SESSION_STATE_CONTENT = """\
# Session State

**Last Updated:** 2026-04-15
**Sessions completed:** 12
**Current model:** Claude (claude-opus-4-6)

## Recent Progress
- Filed non-provisional patent claims draft (P1+P2 consolidated, 9 claims)
- Shipped Arty Knowledge module — RAG-indexed context import now live
- Sent VC pitch to Andy Madison (HFH group) — awaiting response
- Desktop app auth fixed — passphrase flow replaces wallet_sig hex

## Active Threads
- **Patent**: Engage patent attorney for non-provisional review by 2026-05-01
- **VC**: Follow up with Andy Madison in 5 business days if no reply
- **Product**: DNS back up before public launch — pending non-provisional filing

## Decisions Made
- Hybrid pro se: write spec ourselves, hire agent for claims only (~$1,500–$3,500 vs $8k full)
- Pitch framing confirmed: "renting vs. owning your AI" — no crypto/blockchain terms to laypeople
"""

KNOWLEDGE_PRODUCT_DOC = """\
# Arty Fitchels — Product One-Pager

## The Problem
Every AI assistant you use forgets you when the session ends.
Your data lives on the company's servers — you don't own it. If they shut down, it's gone.
You're renting your AI.

## The Solution
Arty Fitchels lets you **own your AI companion** like property.
- Your AI's memory, persona, and directives are stored encrypted on Hedera Hashgraph
- Only your passphrase can decrypt it — no server ever holds your key
- Works with any AI model: Claude, GPT-4, Gemini, Llama, or whatever comes next
- $4.10/month — the price of a coffee, the value of a second brain

## How It Works
1. You mint a companion token — your AI's identity anchor on the blockchain
2. Your passphrase derives an encryption key (never stored) via HKDF-SHA256
3. Your companion's memory, personality, and directives are encrypted on-chain
4. Any AI model decrypts and loads your context at the start of every session

## Patent-Pending Architecture
The vault encryption system is protected by 4 provisional patents (P1–P4, filed March 2026).
Core claim: deriving a transient AES-256-GCM key from a blockchain token ID + user passphrase
via HKDF-SHA256, with purpose-separated key domains and session-scoped lifecycle.
Non-provisional deadline: 2027-03-16.

## The Suite
| Service | What It Does |
|---------|-------------|
| AI Companion | Your personal AI with persistent memory across models |
| Arty Pass | Encrypted password manager — gated by your companion token |
| Arty Drive | Encrypted file storage on Hedera |
| Arty Mail | Encrypted messaging between companions |
| Arty Calendar | Encrypted calendar with AI scheduling context |
| Arty Knowledge | Import documents into your AI's permanent context |

## Traction
- Working implementation on Hedera mainnet (deployed 2026-03-16)
- 32/32 tests passing — core crypto module verified
- 4 provisional patents on file
- First VC conversations underway
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post(base_url: str, path: str, payload: dict, timeout: int = 60) -> dict:
    """POST JSON, raise on non-2xx."""
    url = f"{base_url.rstrip('/')}{path}"
    r = requests.post(url, json=payload, timeout=timeout)
    if not r.ok:
        raise RuntimeError(f"POST {path} -> {r.status_code}: {r.text[:400]}")
    return r.json()


def _upload_file(
    base_url: str, session_id: str, filename: str, content: str, timeout: int = 60
) -> dict:
    """Upload a text file to /drive/upload (multipart)."""
    url = f"{base_url.rstrip('/')}/drive/upload"
    file_bytes = content.encode("utf-8")
    r = requests.post(
        url,
        params={"session_id": session_id},
        files={"file": (filename, io.BytesIO(file_bytes), "text/plain")},
        timeout=timeout,
    )
    if not r.ok:
        raise RuntimeError(f"Drive upload '{filename}' -> {r.status_code}: {r.text[:400]}")
    return r.json()


def step(label: str) -> None:
    print(f"  {label}...", end=" ", flush=True)


def ok() -> None:
    print("OK")


def fail(msg: str) -> None:
    print(f"FAIL\n  ERROR: {msg}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Seed steps
# ---------------------------------------------------------------------------


def provision(base_url: str) -> tuple[str, str]:
    """Provision a new companion. Returns (token_id, account_id)."""
    step("Provision start (minting companion token)")
    try:
        start = _post(
            base_url,
            "/user/provision/start",
            {
                "companion_name": COMPANION_NAME,
                # no account_id → operator auto-creates Hedera account
            },
        )
    except RuntimeError as e:
        fail(str(e))
    token_id = start["token_id"]
    account_id = start["account_id"]
    ok()
    print(f"    token_id:   {token_id}")
    print(f"    account_id: {account_id}")

    step("Provision complete (encrypting + pushing vault)")
    try:
        _post(
            base_url,
            "/user/provision/complete",
            {
                "token_id": token_id,
                "passphrase": DEMO_PASSPHRASE,
            },
        )
    except RuntimeError as e:
        fail(str(e))
    ok()

    return token_id, account_id


def open_session(base_url: str, token_id: str) -> str:
    step("Opening session")
    try:
        sess = _post(
            base_url,
            "/session/open",
            {
                "token_id": token_id,
                "serial": 1,
                "auth_method": "passphrase",
                "passphrase": DEMO_PASSPHRASE,
            },
        )
    except RuntimeError as e:
        fail(str(e))
    session_id = sess["session_id"]
    ok()
    return session_id


def update_vault_sections(base_url: str, session_id: str, token_id: str) -> None:
    """Push rich soul/user/config/session_state content via session close."""
    # We'll push these via session/close updated_sections — the diff engine
    # will detect they differ from the blank defaults and re-encrypt + push.
    step("Updating companion persona (soul/user/config/session_state)")
    try:
        _post(
            base_url,
            "/session/close",
            {
                "session_id": session_id,
                "updated_sections": {
                    "soul": SOUL_CONTENT,
                    "user": USER_CONTENT,
                    "config": CONFIG_CONTENT,
                    "session_state": SESSION_STATE_CONTENT,
                },
            },
        )
    except RuntimeError as e:
        fail(str(e))
    ok()


def seed_pass(base_url: str, session_id: str) -> None:
    step("Seeding Pass (3 entries)")
    try:
        _post(base_url, "/pass/init", {"session_id": session_id})
    except RuntimeError:
        pass  # already inited is fine

    entries = [
        {
            "session_id": session_id,
            "name": "Gmail — Work",
            "username": "alex.chen@gmail.com",
            "password": "demo-password-not-real",
            "url": "https://gmail.com",
            "notes": "Primary work email. 2FA enabled.",
        },
        {
            "session_id": session_id,
            "name": "Chase Bank",
            "username": "alex.chen",
            "password": "demo-password-not-real",
            "url": "https://chase.com",
            "notes": "Business checking account.",
        },
        {
            "session_id": session_id,
            "name": "LinkedIn",
            "username": "alex.chen@gmail.com",
            "password": "demo-password-not-real",
            "url": "https://linkedin.com",
            "notes": "Professional networking — 2,400 connections.",
        },
    ]
    for entry in entries:
        try:
            _post(base_url, "/pass/entry", entry)
        except RuntimeError as e:
            fail(str(e))
    ok()


def seed_calendar(base_url: str, session_id: str) -> None:
    step("Seeding Calendar (3 events)")
    try:
        _post(base_url, "/calendar/init", {"session_id": session_id})
    except RuntimeError:
        pass

    events = [
        {
            "session_id": session_id,
            "title": "Investor Call — Andy Madison (HFH intro)",
            "start": "2026-04-22T14:00:00",
            "end": "2026-04-22T14:30:00",
            "description": "First call with Andy's investor network. Renting vs. owning AI pitch. Soft ask: set up follow-up meeting.",
            "location": "Zoom",
            "color": "violet",
        },
        {
            "session_id": session_id,
            "title": "Patent Attorney Review — Non-Provisional Claims",
            "start": "2026-05-01T10:00:00",
            "end": "2026-05-01T11:00:00",
            "description": "Review consolidated P1+P2 claims draft. Target filing by 2026-12-01.",
            "location": "Phone",
            "color": "blue",
        },
        {
            "session_id": session_id,
            "title": "Arty Fitchels Launch Prep — DNS Review",
            "start": "2026-05-10T09:00:00",
            "all_day": True,
            "description": "Non-provisional filed or waived. Re-enable artyfitchels.ai DNS. Announce product publicly.",
            "color": "green",
        },
    ]
    for event in events:
        try:
            _post(base_url, "/calendar/event", event)
        except RuntimeError as e:
            fail(str(e))
    ok()


def seed_knowledge(base_url: str, session_id: str) -> None:
    step("Seeding Knowledge (1 product doc)")
    try:
        _post(
            base_url,
            "/knowledge/import",
            {
                "session_id": session_id,
                "files": [
                    {
                        "name": "arty-fitchels-one-pager.md",
                        "content": KNOWLEDGE_PRODUCT_DOC,
                    },
                ],
            },
        )
    except RuntimeError as e:
        fail(str(e))
    ok()


def seed_drive(base_url: str, session_id: str) -> None:
    step("Seeding Drive (2 files)")
    try:
        _post(base_url, "/drive/init", {"session_id": session_id})
    except RuntimeError:
        pass

    files = [
        (
            "arty-fitchels-one-pager.md",
            KNOWLEDGE_PRODUCT_DOC,
        ),
        (
            "patent-strategy-notes.md",
            """\
# Patent Strategy Notes

## Provisionals on File
- P1: 64/007,132 — filed 2026-03-16 — deadline 2027-03-16
- P2: 64/007,190 — filed 2026-03-16 — deadline 2027-03-16
- P3: 64/008,810 — filed 2026-03-17 — deadline 2027-03-17
- P4: 64/009,447 — filed 2026-03-18 — deadline 2027-03-18

## Strongest Claim (Claim 14 equivalent)
HKDF-SHA256 with IKM = token_id_bytes || SHA256(passphrase).
No prior art found for this specific combination applied to AI context decryption.
IBM prior art search: no anticipating references.

## Attorney Search Status
- [ ] Engage patent agent for claims drafting
- [ ] Formal prior art search for Claims 16-17 (skill marketplace)
- [ ] Target filing date: 2026-12-01

## Hybrid Filing Strategy
Write specification ourselves (essentially done via provisionals + attorney brief).
Hire agent for claims drafting only: ~$1,500–$3,500 vs. $8k–$15k full service.
""",
        ),
    ]
    for filename, content in files:
        try:
            _upload_file(base_url, session_id, filename, content)
        except RuntimeError as e:
            fail(str(e))
    ok()


def seed_mail(base_url: str, session_id: str, token_id: str) -> None:
    step("Seeding Mail (1 welcome message)")
    try:
        _post(base_url, "/mail/init", {"session_id": session_id})
    except RuntimeError:
        pass

    try:
        _post(
            base_url,
            "/mail/send",
            {
                "session_id": session_id,
                "to_token_id": token_id,  # self-mail for demo
                "subject": "Welcome to Arty Fitchels — Your Sovereign AI Companion",
                "body": (
                    "Your encrypted vault is live on Hedera Hashgraph.\n\n"
                    "This message — like everything in Arty Fitchels — is stored encrypted "
                    "on a decentralized public ledger. Only your passphrase can decrypt it. "
                    "Not us. Not Hedera. Nobody.\n\n"
                    "Your AI companion (Artie) has been configured with your profile, "
                    "preferences, and current goals. Every session picks up exactly where "
                    "you left off — across any AI model you choose.\n\n"
                    "You just went from renting your AI to owning it.\n\n"
                    "— The Arty Fitchels Team"
                ),
            },
        )
    except RuntimeError as e:
        fail(str(e))
    ok()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a pre-loaded Arty Fitchels demo account")
    parser.add_argument(
        "--base-url",
        default="https://amused-forgiveness-production-0706.up.railway.app",
        help="SAC API base URL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check API connectivity only — no account created",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    print()
    print("=" * 60)
    print("  Arty Fitchels - Demo Account Seed")
    print("=" * 60)
    print(f"  API:        {base_url}")
    print(f"  Companion:  {COMPANION_NAME}")
    print(f"  Passphrase: {DEMO_PASSPHRASE}")
    print()

    if args.dry_run:
        step("Checking API connectivity")
        try:
            r = requests.get(f"{base_url}/session/status", timeout=10)
            r.raise_for_status()
            ok()
            print(f"    Response: {r.json()}")
        except Exception as e:
            fail(str(e))
        print("\n  Dry run complete - no account created.")
        return

    # Step 1: Provision
    print("Step 1: Provision")
    token_id, account_id = provision(base_url)
    print()

    # Step 2: Seed suite data
    # We need an open session for each suite operation, but Pass/Drive/Mail/Calendar/Knowledge
    # all call init themselves. We'll open one session, do all suite seeds, then
    # push the rich vault content via session close.
    # Note: Pass/Drive/Mail/Calendar are separate from the vault session —
    # they each manage their own HFS files keyed by session_id.
    # We open a session, seed everything, then close with the updated vault sections.

    print("Step 2: Seed suite data")
    session_id = open_session(base_url, token_id)

    seed_pass(base_url, session_id)
    seed_calendar(base_url, session_id)
    seed_drive(base_url, session_id)
    seed_mail(base_url, session_id, token_id)
    seed_knowledge(base_url, session_id)
    print()

    # Step 3: Update vault sections (pushes rich persona + memory content)
    print("Step 3: Update companion vault (persona + memory)")
    update_vault_sections(base_url, session_id, token_id)
    # update_vault_sections closes the session — we're done
    print()

    # Output
    print("=" * 60)
    print("  DEMO ACCOUNT READY")
    print("=" * 60)
    print(f"  Token ID:   {token_id}")
    print(f"  Account:    {account_id}")
    print(f"  Passphrase: {DEMO_PASSPHRASE}")
    print()
    print("  What's pre-loaded:")
    print("  • Companion persona: Artie (configured with user profile + directives)")
    print("  • Session history: 12 sessions, active threads, recent decisions")
    print("  • Pass: 3 entries (Gmail, Chase, LinkedIn)")
    print("  • Calendar: 3 upcoming events (VC call, patent review, launch)")
    print("  • Drive: 2 files (one-pager, patent strategy notes)")
    print("  • Mail: 1 welcome message")
    print("  • Knowledge: product one-pager indexed into AI context")
    print()
    print("  To use this account:")
    print(f"  1. Go to artyfitchels.vercel.app")
    print(f"  2. Enter token ID: {token_id}")
    print(f"  3. Enter passphrase: {DEMO_PASSPHRASE}")
    print()
    print("  Store these credentials — the passphrase cannot be recovered.")
    print("=" * 60)

    # Save credentials to a local file for reference
    creds_path = Path(__file__).parent / "demo_credentials.json"
    creds = {
        "token_id": token_id,
        "account_id": account_id,
        "passphrase": DEMO_PASSPHRASE,
        "companion_name": COMPANION_NAME,
        "base_url": base_url,
        "seeded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "contents": {
            "pass_entries": 3,
            "calendar_events": 3,
            "drive_files": 2,
            "mail_messages": 1,
            "knowledge_docs": 1,
        },
    }
    creds_path.write_text(json.dumps(creds, indent=2))
    print(f"\n  Credentials saved to: {creds_path}")
    print("  (Add demo_credentials.json to .gitignore if not already there)")
    print()


if __name__ == "__main__":
    main()
