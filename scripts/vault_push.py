"""
vault_push.py — Push Symbiote Vault to Hedera

Encrypts core identity files and stores them on Hedera File Service (HFS),
gated by the context token. Registers the vault index in the ContextValidator
contract on-chain.

Phase 1 sections pushed:
 soul -> Knowledge/SOUL.md
 user -> Personas/USER.md
 symbiote -> Personas/Symbiote.md
 session_state -> System/Session-State.md

Usage:
 cd D:\\code\\sovereign-ai-context
 python scripts/vault_push.py
 python scripts/vault_push.py --force-new # fresh HFS files (re-register contract)
 python scripts/vault_push.py --section soul # push one section only
 python scripts/vault_push.py --dry-run # show what would be pushed

Requirements:
 .env must contain: OPERATOR_ID, OPERATOR_KEY, SOUL_TOKEN_ID, VALIDATOR_CONTRACT_ID
"""

import argparse
import hashlib
import sys
import os
from pathlib import Path

# Make sure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.vault import (
 VAULT_ROOT,
 VAULT_SECTIONS,
 VAULT_DIRS,
 VAULT_DIR_OPTIONS,
 SOUL_TOKEN_ID,
 push_all,
 push_section,
 get_vault_key,
 load_local_index,
 save_local_index,
)
from src.event_log import log_event
# session_guard provides start-hash helpers — import lazily to avoid hard dep
try:
 from scripts.session_guard import local_section_hashes, load_start_hashes
except ImportError:
 from session_guard import local_section_hashes, load_start_hashes


def dry_run() -> None:
 """Show what would be pushed without doing anything."""
 print("\n[DRY RUN] Vault push preview:")
 print(f" Vault root: {VAULT_ROOT}")
 print(f" Context token: {SOUL_TOKEN_ID}")

 print(f"\n Identity sections ({len(VAULT_SECTIONS)}):")
 for section_name, rel_path in VAULT_SECTIONS.items():
 local_path = VAULT_ROOT / rel_path
 size = local_path.stat().st_size if local_path.exists() else None
 status = f"{size:,} bytes" if size else "NOT FOUND"
 print(f" [{section_name}] {rel_path} ({status})")

 print(f"\n Directory bundles ({len(VAULT_DIRS)}):")
 for dir_name, rel_dir in VAULT_DIRS.items():
 dir_path = VAULT_ROOT / rel_dir
 options = VAULT_DIR_OPTIONS.get(dir_name, {})
 recursive = options.get("recursive", True)
 if dir_path.is_dir():
 file_iter = sorted(dir_path.rglob("*")) if recursive else sorted(dir_path.glob("*"))
 count = sum(1 for f in file_iter if f.is_file() and f.suffix == ".md")
 depth = "recursive" if recursive else "root-level only"
 print(f" [{dir_name}] {rel_dir}/ ({count} .md files, {depth})")
 else:
 print(f" [{dir_name}] {rel_dir}/ (NOT FOUND)")

 local = load_local_index()
 if local:
 print(f"\n Existing index cache: {local.get('index_file_id', 'none')}")
 cached_sections = list(local.get("sections", {}).keys())
 cached_dirs = list(local.get("dir_sections", {}).keys())
 print(f" Cached sections: {cached_sections}")
 print(f" Cached dir bundles: {cached_dirs}")
 else:
 print("\n No existing local index — new HFS files will be created.")


def push_single_section(section_name: str) -> None:
 """Push a single vault section, updating the local index."""
 if section_name not in VAULT_SECTIONS:
 print(f"Unknown section '{section_name}'. Valid: {list(VAULT_SECTIONS.keys())}")
 sys.exit(1)

 token_id = SOUL_TOKEN_ID
 key = get_vault_key(token_id)
 local = load_local_index()
 existing_section_ids = local.get("sections", {})

 rel_path = VAULT_SECTIONS[section_name]
 local_path = VAULT_ROOT / rel_path
 if not local_path.exists():
 print(f"File not found: {local_path}")
 sys.exit(1)

 content = local_path.read_bytes()
 print(f"\n[vault] Pushing section '{section_name}' ({len(content)} bytes)...")

 existing_file_id = existing_section_ids.get(section_name)
 file_id = push_section(section_name, content, key, token_id, existing_file_id)

 # Update local index cache
 local.setdefault("sections", {})[section_name] = file_id
 local["token_id"] = token_id
 save_local_index(local)
 print(f"\n[vault] Section '{section_name}' pushed: {file_id}")


def _log_session_ended() -> None:
 """
 Log SESSION_ENDED to HCS with a delta between session-start and session-end hashes.

 Closes the audit loop opened by session_guard.py's SESSION_STARTED event.
 Any section that changed during the session is listed in `changed_sections`.
 This creates an immutable on-chain record of exactly what was modified.

 Gracefully skips if .session_start_hashes.json is missing (guard didn't run).
 """
 start_data = load_start_hashes()
 if not start_data:
 # session_guard.py didn't run this session — log minimal close event
 log_event(
 event_type="SESSION_ENDED",
 payload={
 "token_id": SOUL_TOKEN_ID,
 "delta_available": False,
 },
 )
 return

 start_hashes: dict[str, str] = start_data.get("hashes", {})
 end_hashes = local_section_hashes()

 changed: list[str] = []
 for section_name, end_hash in end_hashes.items():
 start_hash = start_hashes.get(section_name, "")
 if start_hash != end_hash:
 changed.append(section_name)

 log_event(
 event_type="SESSION_ENDED",
 payload={
 "token_id": SOUL_TOKEN_ID,
 "session_opened_at": start_data.get("timestamp"),
 "delta_available": True,
 "changed_sections": changed,
 "unchanged_sections": [s for s in end_hashes if s not in changed],
 "end_hashes": end_hashes,
 },
 )

 if changed:
 print(f"\n[session-guard] SESSION_ENDED logged — {len(changed)} section(s) changed: {changed}")
 else:
 print(f"\n[session-guard] SESSION_ENDED logged — no sections changed.")


def main():
 parser = argparse.ArgumentParser(
 description="Push Symbiote Vault to Hedera HFS",
 formatter_class=argparse.RawDescriptionHelpFormatter,
 epilog="""
Examples:
 python scripts/vault_push.py # push all sections
 python scripts/vault_push.py --force-new # force new HFS files
 python scripts/vault_push.py --section soul # push one section
 python scripts/vault_push.py --dry-run # show what would be pushed
 """,
 )
 parser.add_argument(
 "--force-new",
 action="store_true",
 help="Create new HFS files even if index already exists",
 )
 parser.add_argument(
 "--section",
 type=str,
 default=None,
 help=f"Push a single section only. One of: {list(VAULT_SECTIONS.keys())}",
 )
 parser.add_argument(
 "--dry-run",
 action="store_true",
 help="Show what would be pushed without actually pushing",
 )

 args = parser.parse_args()

 if args.dry_run:
 dry_run()
 return

 if args.section:
 push_single_section(args.section)
 return

 # Full push
 print("=" * 60)
 print(" Symbiote Vault -> Hedera HFS (Phase 1 Migration)")
 print("=" * 60)
 result = push_all(force_new=args.force_new)

 print("\n" + "=" * 60)
 print(" PUSH SUMMARY")
 print("=" * 60)
 print(f" Context token: {SOUL_TOKEN_ID}")
 print(f" Index file: {result.get('index', 'n/a')}")
 print(f"\n Identity sections:")
 for section_name in VAULT_SECTIONS:
 fid = result.get(section_name, "skipped")
 print(f" {section_name:<16} {fid}")
 print(f"\n Directory bundles:")
 for dir_name in VAULT_DIRS:
 fid = result.get(dir_name, "skipped")
 print(f" {dir_name:<16} {fid}")
 print("=" * 60)
 print("\nVault pushed to Hedera. Run vault_pull.py to verify.")

 # Session end audit — compare final state against session-start hashes
 _log_session_ended()


if __name__ == "__main__":
 main()
