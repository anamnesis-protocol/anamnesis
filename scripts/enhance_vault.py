#!/usr/bin/env python3
"""
enhance_vault.py — CLI tool for vault enhancement

Usage:
    python scripts/enhance_vault.py <vault_path> [--dry-run] [--no-xrefs] [--no-metadata]

Examples:
    # Dry run to preview changes
    python scripts/enhance_vault.py d:/my_vault --dry-run

    # Full enhancement
    python scripts/enhance_vault.py d:/my_vault

    # Only add metadata, skip cross-references
    python scripts/enhance_vault.py d:/my_vault --no-xrefs
"""

import sys
from pathlib import Path
import argparse

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vault_enhancements import batch_enhance_vault


def main():
    parser = argparse.ArgumentParser(
        description="Enhance vault with automated metadata and cross-references"
    )
    parser.add_argument("vault_path", type=Path, help="Path to vault directory")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without writing files"
    )
    parser.add_argument(
        "--no-xrefs", action="store_true", help="Skip adding cross-reference sections"
    )
    parser.add_argument(
        "--no-metadata", action="store_true", help="Skip metadata generation/updates"
    )

    args = parser.parse_args()

    if not args.vault_path.exists():
        print(f"❌ Error: Vault path does not exist: {args.vault_path}")
        sys.exit(1)

    if not args.vault_path.is_dir():
        print(f"❌ Error: Path is not a directory: {args.vault_path}")
        sys.exit(1)

    print(f"🔍 Analyzing vault: {args.vault_path}")
    if args.dry_run:
        print("   (DRY RUN - no files will be modified)")

    summary = batch_enhance_vault(
        args.vault_path,
        dry_run=args.dry_run,
        add_xrefs=not args.no_xrefs,
        update_metadata=not args.no_metadata,
    )

    print("\n📊 Enhancement Summary:")
    print(f"   Total files: {summary['total_files']}")
    print(f"   Enhanced: {summary['enhanced']}")
    print(f"   Metadata generated: {summary['metadata_generated']}")
    print(f"   Cross-references added: {summary['xrefs_added']}")
    print(f"   Total references detected: {summary['total_references']}")

    if summary["errors"]:
        print(f"\n⚠️  Errors ({len(summary['errors'])}):")
        for error in summary["errors"][:10]:  # Show first 10
            print(f"   - {error}")
        if len(summary["errors"]) > 10:
            print(f"   ... and {len(summary['errors']) - 10} more")

    if args.dry_run:
        print("\n💡 Run without --dry-run to apply changes")
    else:
        print("\n✅ Vault enhancement complete!")


if __name__ == "__main__":
    main()
