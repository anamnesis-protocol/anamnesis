"""
package_push.py — Push Vault Memory Packages to Hedera

Encrypts session archives, research files, and project files and stores
them as individually-addressable memory packages on Hedera File Service.
A package index is built and its file_id stored inside the vault index,
so a single contract lookup reaches all vault data.

Categories:
 sessions -> Archive/*.md (episodic memory)
 research -> Research/*.md (semantic memory)
 projects -> 02 - Projects/*.md (semantic memory)

Usage:
 cd D:\\code\\sovereign-ai-context
 python scripts/package_push.py # push all categories
 python scripts/package_push.py --category sessions # one category
 python scripts/package_push.py --force-new # fresh HFS files
 python scripts/package_push.py --dry-run # show what would be pushed
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.memory_packages import (
    PACKAGE_CATEGORIES,
    SKIP_NAMES,
    SKIP_EXTENSIONS,
    push_all_packages,
)


def dry_run(categories: list[str]) -> None:
    """Show what would be pushed without doing anything."""
    total_files = 0
    total_bytes = 0

    print(f"\n[DRY RUN] Package categories to push: {categories}")
    for cat in categories:
        cat_dir = PACKAGE_CATEGORIES.get(cat)
        if not cat_dir or not cat_dir.exists():
            print(f"\n [{cat}] NOT FOUND: {cat_dir}")
            continue

        files = [
            f
            for f in sorted(cat_dir.iterdir())
            if f.is_file()
            and f.name not in SKIP_NAMES
            and f.suffix not in SKIP_EXTENSIONS
            and f.stat().st_size > 0
        ]

        cat_bytes = sum(f.stat().st_size for f in files)
        total_files += len(files)
        total_bytes += cat_bytes

        print(f"\n [{cat}] {len(files)} files ({cat_bytes:,} bytes)")
        for f in files:
            print(f" {f.name} ({f.stat().st_size:,} bytes)")

    print(f"\n Total: {total_files} packages, {total_bytes:,} bytes")
    print(f" HFS files that would be created: {total_files + 1} (+ package index)")


def main():
    parser = argparse.ArgumentParser(
        description="Push Symbiote Vault memory packages to Hedera HFS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/package_push.py                     # push all categories
  python scripts/package_push.py --category sessions  # episodic only
  python scripts/package_push.py --category research  # semantic research only
  python scripts/package_push.py --category projects  # semantic projects only
  python scripts/package_push.py --force-new          # fresh HFS files for all
  python scripts/package_push.py --dry-run            # preview only
        """,
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        choices=list(PACKAGE_CATEGORIES.keys()),
        help="Push a single category only",
    )
    parser.add_argument(
        "--force-new",
        action="store_true",
        help="Create new HFS files even if packages already exist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be pushed without actually pushing",
    )

    args = parser.parse_args()
    categories = [args.category] if args.category else list(PACKAGE_CATEGORIES.keys())

    if args.dry_run:
        dry_run(categories)
        return

    print("=" * 60)
    print(" Symbiote Vault Memory Packages -> Hedera HFS")
    print(" Phase 2: Episodic + Semantic Memory Layer")
    print("=" * 60)
    print(f" Categories: {categories}")

    index_file_id = push_all_packages(
        categories=categories,
        force_new=args.force_new,
    )

    print("\n" + "=" * 60)
    print(" PHASE 2 COMPLETE")
    print("=" * 60)
    print(f" Package index: {index_file_id}")
    print(f" Vault index updated with packages pointer")
    print(f"\nRun package_query.py to test relevance-gated loading.")
    print("=" * 60)


if __name__ == "__main__":
    main()
