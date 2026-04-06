"""
push_drake_vault.py — Push Drake local vault to Hedera testnet.

Maps the Drake vault files to the SaaS section names and pushes them
to HFS, encrypted with the operator key (same key derivation as demo sign).

Usage:
    cd D:\\code\\sovereign-ai-context
    python scripts/push_drake_vault.py
    python scripts/push_drake_vault.py --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(".env.testnet", override=True)

# Point vault at the Drake local vault
DRAKE_VAULT = Path("D:/symbiote_suit")

SECTION_MAP = {
    "harness": DRAKE_VAULT / "Knowledge/SOUL.md",
    "user": DRAKE_VAULT / "Personas/USER.md",
    "config": DRAKE_VAULT / "Personas/Symbiote.md",
    "session_state": DRAKE_VAULT / "System/Session-State.md",
}

TOKEN_ID = "0.0.8252163"


def main():
    parser = argparse.ArgumentParser(description="Push Drake vault to Hedera testnet")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be pushed")
    parser.add_argument(
        "--force-new", action="store_true", help="Create fresh HFS files (ignore local cache)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print(" Drake Vault -> Hedera HFS (testnet)")
    print("=" * 60)
    print(f" Token: {TOKEN_ID}")
    print(f" Vault: {DRAKE_VAULT}")
    print()

    # Verify all files exist
    missing = []
    for name, path in SECTION_MAP.items():
        exists = path.exists()
        size = f"{path.stat().st_size:,} bytes" if exists else "NOT FOUND"
        print(f"  [{name}] {path.relative_to(DRAKE_VAULT)} ({size})")
        if not exists:
            missing.append(name)

    if missing:
        print(f"\nERROR: Missing files for sections: {missing}")
        sys.exit(1)

    if args.dry_run:
        print("\n[DRY RUN] No changes made.")
        return

    print()

    # Override vault.py env vars before importing
    import json

    os.environ["VAULT_ROOT"] = str(DRAKE_VAULT)
    os.environ["CONTEXT_TOKEN_ID"] = TOKEN_ID
    os.environ["VAULT_SECTIONS_JSON"] = json.dumps(
        {name: str(path.relative_to(DRAKE_VAULT)) for name, path in SECTION_MAP.items()}
    )

    from src.vault import push_all

    result = push_all(force_new=args.force_new)

    print("\n" + "=" * 60)
    print(" PUSH COMPLETE")
    print("=" * 60)
    print(f" Index file: {result.get('index', 'n/a')}")
    for section in SECTION_MAP:
        fid = result.get(section, "skipped")
        print(f"  {section:<16} {fid}")
    print("=" * 60)
    print("\nVault updated. Restart uvicorn and open a new session to see the changes.")


if __name__ == "__main__":
    main()
