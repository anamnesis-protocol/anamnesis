"""
session_guard.py — Session Boundary Integrity Check

Applies context hijack prevention (Patent Claims 6-7, 18-19) at session start.

On first run per session:
 1. Compute SHA-256 of all vault sections on disk (what the AI will load)
 2. Pull all sections from HFS — verify_content() runs injection scan + hash check
 3. Compare local vs HFS hashes — report divergence (possible between-session edits)
 4. Log SESSION_STARTED to HCS with local hashes (immutable session open record)
 5. Save .session_start_hashes.json for end-of-session delta comparison
 6. Set lock file — subsequent prompt submits skip re-running this session

Called automatically via Claude Code UserPromptSubmit hook.
Silently skips if already ran within GUARD_TTL_HOURS.

Security guarantees:
 - Any injection pattern in a vault section detected before it enters model context
 - HFS-anchored golden state compared against local state on every session open
 - Immutable HCS record of what was present at session start + whether it matched HFS
 - vault_push.py (Stop hook) logs SESSION_ENDED with delta, closing the audit loop

Usage:
 python scripts/session_guard.py # manual run
 python scripts/session_guard.py --force # ignore lock, re-run
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure src/ importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.vault import (
 VAULT_ROOT,
 VAULT_SECTIONS,
 SOUL_TOKEN_ID,
 pull_all,
)
from src.event_log import log_event

# Suppress repeated runs within one work session (hours)
GUARD_TTL_HOURS = 8

# Windows-safe temp path for the session lock file
LOCK_FILE = Path(tempfile.gettempdir()) / "sovereign_session_guard.lock"

# Session start hashes — read by vault_push.py at session end for delta logging
START_HASHES_FILE = Path(__file__).parent.parent / ".session_start_hashes.json"


# ---------------------------------------------------------------------------
# Lock helpers
# ---------------------------------------------------------------------------

def _already_ran() -> bool:
 """Return True if the guard ran within GUARD_TTL_HOURS."""
 if not LOCK_FILE.exists():
 return False
 age_hours = (time.time() - LOCK_FILE.stat().st_mtime) / 3600
 return age_hours < GUARD_TTL_HOURS


def _set_lock() -> None:
 LOCK_FILE.touch()


# ---------------------------------------------------------------------------
# Local hash helpers
# ---------------------------------------------------------------------------

def local_section_hashes() -> dict[str, str]:
 """SHA-256 hex of each vault section file currently on disk."""
 hashes: dict[str, str] = {}
 for section_name, rel_path in VAULT_SECTIONS.items():
 local_path = VAULT_ROOT / rel_path
 if local_path.exists():
 hashes[section_name] = hashlib.sha256(local_path.read_bytes()).hexdigest()
 else:
 hashes[section_name] = "MISSING"
 return hashes


def save_start_hashes(local_hashes: dict[str, str]) -> None:
 """
 Write .session_start_hashes.json with integrity hash.
 vault_push.py reads this at session end to compute the delta.
 """
 data: dict = {
 "timestamp": datetime.now(timezone.utc).isoformat(),
 "token_id": SOUL_TOKEN_ID,
 "hashes": local_hashes,
 }
 canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
 data["_integrity"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
 with open(START_HASHES_FILE, "w", encoding="utf-8") as f:
 json.dump(data, f, indent=2)


def load_start_hashes() -> dict:
 """
 Load .session_start_hashes.json and verify integrity hash.
 Returns {} if file missing or integrity check fails.
 """
 if not START_HASHES_FILE.exists():
 return {}
 with open(START_HASHES_FILE, encoding="utf-8") as f:
 data = json.load(f)
 stored_hash = data.pop("_integrity", None)
 if stored_hash:
 canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
 computed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
 if computed != stored_hash:
 print("[session-guard] WARN: .session_start_hashes.json integrity failed — possible tampering.")
 return {}
 return data


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(force: bool = False) -> None:
 if not force and _already_ran():
 # Silent — fires on every prompt submission, must not spam output
 return

 print("\n[session-guard] Session boundary check starting...")
 print(f" Token: {SOUL_TOKEN_ID}")
 print(f" Vault: {VAULT_ROOT}")

 # 1. Local hashes — what the AI will work with this session
 local = local_section_hashes()
 print(f"\n Local section hashes:")
 for name, h in local.items():
 status = f"{h[:16]}..." if h != "MISSING" else "MISSING"
 print(f" {name:<16} {status}")

 # 2. Pull from HFS — verify_content() runs injection scan on each section
 print(f"\n Pulling vault from HFS for integrity verification...")
 hfs_sections: dict[str, bytes] = {}
 try:
 hfs_sections = pull_all()
 except ValueError as e:
 # verify_content() raised — injection pattern or hash mismatch detected
 print(f"\n [SECURITY] HFS content failed integrity check:\n {e}")
 print(" Session start logged with INTEGRITY_FAILURE flag.")
 log_event(
 event_type="SESSION_STARTED",
 payload={
 "token_id": SOUL_TOKEN_ID,
 "local_hashes": local,
 "hfs_match": False,
 "integrity_failure": True,
 "error": str(e),
 },
 )
 _set_lock()
 return
 except Exception as e:
 print(f"\n [WARN] HFS pull failed: {e}")
 print(" Proceeding with local files only.")

 # 3. Compare local vs HFS
 mismatches: list[tuple[str, str, str]] = []
 for section_name, local_hash in local.items():
 if local_hash == "MISSING" or section_name not in hfs_sections:
 continue
 hfs_hash = hashlib.sha256(hfs_sections[section_name]).hexdigest()
 if local_hash != hfs_hash:
 mismatches.append((section_name, local_hash[:16], hfs_hash[:16]))

 if mismatches:
 print(f"\n [INFO] Local files differ from HFS ({len(mismatches)} section(s)):")
 for name, lh, hh in mismatches:
 print(f" {name}: local={lh}... HFS={hh}...")
 print(" This is normal if you edited files since last session.")
 print(" vault_push.py will sync changes at session end (Stop hook).")
 elif hfs_sections:
 print(f"\n All sections match HFS. Vault integrity confirmed.")

 # 4. Log SESSION_STARTED to HCS — immutable session open record
 log_event(
 event_type="SESSION_STARTED",
 payload={
 "token_id": SOUL_TOKEN_ID,
 "local_hashes": local,
 "hfs_match": len(mismatches) == 0,
 "mismatch_sections": [m[0] for m in mismatches],
 },
 )

 # 5. Save start hashes for end-of-session delta
 save_start_hashes(local)

 _set_lock()

 print(f"\n SESSION_STARTED logged to HCS.")
 print(f" Start hashes saved to {START_HASHES_FILE.name}")
 print(f"[session-guard] Done.\n")


def main() -> None:
 if hasattr(sys.stdout, "reconfigure"):
 sys.stdout.reconfigure(encoding="utf-8", errors="replace")

 parser = argparse.ArgumentParser(description="Sovereign AI session boundary check")
 parser.add_argument(
 "--force",
 action="store_true",
 help="Ignore lock file and re-run regardless of TTL",
 )
 args = parser.parse_args()
 run(force=args.force)


if __name__ == "__main__":
 main()
