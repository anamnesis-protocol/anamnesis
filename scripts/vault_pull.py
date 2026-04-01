"""
vault_pull.py — Pull Symbiote Vault from Hedera

Validates the context token, fetches the encrypted vault index from HFS,
decrypts and loads vault sections. Can write decrypted files to an output
directory for inspection or restore.

Usage:
 cd D:\\code\\sovereign-ai-context
 python scripts/vault_pull.py # verify all sections (no file write)
 python scripts/vault_pull.py --out ./vault_restore # decrypt and write files
 python scripts/vault_pull.py --section soul # pull one section
 python scripts/vault_pull.py --section soul --out . # pull and write soul.md

Requirements:
 .env must contain: OPERATOR_ID, OPERATOR_KEY, SOUL_TOKEN_ID, VALIDATOR_CONTRACT_ID
 vault_push.py must have been run at least once to create the on-chain index.
"""

import argparse
import sys
from pathlib import Path

# Make sure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.vault import (
 VAULT_ROOT,
 VAULT_SECTIONS,
 VAULT_DIRS,
 SOUL_TOKEN_ID,
 SOUL_TOKEN_SERIAL,
 pull_all,
 pull_section,
 pull_dir_section,
 pull_index,
 get_vault_key,
 get_section_key,
 load_local_index,
)
from src.contract import (
 token_id_to_evm_address,
 get_registered_file_id,
)
from src.config import get_validator_contract_id


def verify_contract_registration() -> str:
 """
 Confirm the vault index is registered in the ContextValidator contract.
 Returns the registered index file_id.
 """
 contract_id = get_validator_contract_id()
 token_evm = token_id_to_evm_address(SOUL_TOKEN_ID)
 file_id = get_registered_file_id(contract_id, token_evm, SOUL_TOKEN_SERIAL)

 if file_id:
 print(f" Contract {contract_id}: index registered -> {file_id} [OK]")
 else:
 print(f" Contract {contract_id}: NO index registered")
 print(" Run vault_push.py first.")
 sys.exit(1)

 return file_id


def pull_one_section(section_name: str, out_dir: Path | None) -> None:
 """Pull and optionally write a single vault section."""
 if section_name not in VAULT_SECTIONS:
 print(f"Unknown section '{section_name}'. Valid: {list(VAULT_SECTIONS.keys())}")
 sys.exit(1)

 token_id = SOUL_TOKEN_ID
 key = get_vault_key(token_id)

 # Get section file_id from local index
 local = load_local_index()
 section_ids = local.get("sections", {})

 if section_name not in section_ids:
 # Fall back: pull full index from HFS
 print(f" Section '{section_name}' not in local cache — fetching index from HFS...")
 index_file_id = local.get("index_file_id")
 if not index_file_id:
 index_file_id = verify_contract_registration()
 section_ids = pull_index(index_file_id, key, token_id)

 file_id = section_ids.get(section_name)
 if not file_id:
 print(f" Section '{section_name}' not found in vault index.")
 sys.exit(1)

 print(f"\n[vault] Pulling section '{section_name}' from {file_id}...")
 content = pull_section(file_id, key, token_id)
 print(f" {len(content)} bytes decrypted")

 if out_dir:
 out_dir.mkdir(parents=True, exist_ok=True)
 out_path = out_dir / f"{section_name}.md"
 out_path.write_bytes(content)
 print(f" Written: {out_path}")
 else:
 # Print first 500 chars as preview
 preview = content.decode("utf-8", errors="replace")[:500]
 print(f"\n--- {section_name} preview ---")
 print(preview)
 if len(content) > 500:
 print(f"... [{len(content) - 500} more bytes]")


def _pull_dir_sections(restore_root: Path) -> None:
 """
 Fetch and restore all directory bundles (Research, Projects, System) from HFS.

 Each bundle is decrypted and unpacked to restore_root/Research/, etc.
 Use this for disaster recovery — restores working files from HFS.
 """
 token_id = SOUL_TOKEN_ID
 section_key = get_section_key(token_id)
 local = load_local_index()
 dir_ids: dict[str, str] = local.get("dir_sections", {})

 if not dir_ids:
 print("\n[vault] No directory bundles found in local cache.")
 print(" Run vault_push.py first, or check that --force-new was not used.")
 return

 print("\n" + "=" * 60)
 print(" DIRECTORY BUNDLE RESTORE")
 print("=" * 60)
 print(f" Restore root: {restore_root}")

 for dir_name, file_id in dir_ids.items():
 # dir_name is "dir:research" — strip prefix for output dir
 subdir_key = dir_name.split(":", 1)[-1] # "research"
 # Map back to original vault dir name
 rel_dir = VAULT_DIRS.get(dir_name, subdir_key)
 output_dir = restore_root / rel_dir
 output_dir.mkdir(parents=True, exist_ok=True)

 print(f"\n [{dir_name}] -> {file_id}")
 print(f" Restoring to: {output_dir}")
 written = pull_dir_section(dir_name, file_id, section_key, token_id, output_dir)
 print(f" Restored {len(written)} file(s)")
 for path in written[:5]:
 print(f" {path}")
 if len(written) > 5:
 print(f" ... and {len(written) - 5} more")

 print("\n" + "=" * 60)
 print(" Directory bundles restored successfully.")
 print("=" * 60)


def main():
 # Reconfigure stdout to handle Unicode on Windows (cp1252 -> utf-8)
 if hasattr(sys.stdout, "reconfigure"):
 sys.stdout.reconfigure(encoding="utf-8", errors="replace")

 parser = argparse.ArgumentParser(
 description="Pull Symbiote Vault from Hedera HFS",
 formatter_class=argparse.RawDescriptionHelpFormatter,
 epilog="""
Examples:
 python scripts/vault_pull.py # verify all sections
 python scripts/vault_pull.py --out ./vault_restore # decrypt and write files
 python scripts/vault_pull.py --section soul # preview soul section
 python scripts/vault_pull.py --section soul --out . # write soul.md to current dir
 """,
 )
 parser.add_argument(
 "--section",
 type=str,
 default=None,
 help=f"Pull a single section. One of: {list(VAULT_SECTIONS.keys())}",
 )
 parser.add_argument(
 "--out",
 type=str,
 default=None,
 help="Output directory for decrypted files (creates if not exists)",
 )
 parser.add_argument(
 "--verify-contract",
 action="store_true",
 help="Check contract registration before pulling (default: use local cache)",
 )
 parser.add_argument(
 "--dirs",
 action="store_true",
 help="Also pull and restore directory bundles (Research, Projects, System) to vault",
 )
 parser.add_argument(
 "--dirs-out",
 type=str,
 default=None,
 help="Output root for directory restore (defaults to VAULT_ROOT). Only used with --dirs.",
 )

 args = parser.parse_args()
 out_dir = Path(args.out) if args.out else None

 print("=" * 60)
 print(" Hedera HFS -> Symbiote Vault (Pull)")
 print("=" * 60)
 print(f" Context token: {SOUL_TOKEN_ID}")

 if args.verify_contract:
 print("\n[vault] Verifying contract registration...")
 verify_contract_registration()

 if args.section:
 pull_one_section(args.section, out_dir)
 return

 # Full identity section pull (soul, user, symbiote, session_state)
 result = pull_all(output_dir=out_dir)

 print("\n" + "=" * 60)
 print(" IDENTITY SECTIONS")
 print("=" * 60)
 print(f" Context token: {SOUL_TOKEN_ID}")
 for section_name, content in result.items():
 print(f" {section_name:<15} {len(content):,} bytes")
 if out_dir:
 print(f" Written to: {out_dir.resolve()}")
 print("=" * 60)
 print(" Identity sections verified.")

 # Directory bundle restore (opt-in)
 if args.dirs:
 restore_root = Path(args.dirs_out) if args.dirs_out else VAULT_ROOT
 _pull_dir_sections(restore_root)


if __name__ == "__main__":
 main()
