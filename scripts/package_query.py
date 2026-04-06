"""
package_query.py — Relevance-Gated Vault Package Query

Loads the encrypted package index from HFS and queries it by relevance.
Only packages scoring above the threshold are returned — this is the
"relevance-gated memory package loading" from the patent (Claims 8-9).

No unnecessary packages are decrypted or loaded unless explicitly requested
with --fetch, keeping context loading minimal.

Usage:
 cd D:\\code\\sovereign-ai-context
 python scripts/package_query.py "hedera patent PoC"
 python scripts/package_query.py "anygrations business plan" --top 3
 python scripts/package_query.py "sovereign ai context" --fetch
 python scripts/package_query.py "patent" --category sessions
 python scripts/package_query.py --list # list all packages
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.memory_packages import (
    PACKAGE_CATEGORIES,
    pull_package,
    pull_package_index,
    pull_packages_parallel,
    query_packages,
)
from src.vault import get_package_key, load_local_index, CONTEXT_TOKEN_ID


def get_package_index_file_id() -> str:
    """Get the package index file_id from local cache."""
    local = load_local_index()
    file_id = local.get("packages_index_file_id")
    if not file_id:
        print("No package index in local cache. Run package_push.py first.")
        sys.exit(1)
    return file_id


def list_all_packages(packages) -> None:
    """Print a table of all packages in the index."""
    categories = {}
    for pkg in packages:
        categories.setdefault(pkg.category, []).append(pkg)

    for cat, pkgs in sorted(categories.items()):
        print(f"\n [{cat}] {len(pkgs)} packages")
        for p in sorted(pkgs, key=lambda x: x.date, reverse=True):
            print(f" {p.date} {p.name:<50} {p.size:>7,} bytes {p.file_id}")


def main():
    # Reconfigure stdout to handle Unicode on Windows (cp1252 -> utf-8)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Query vault memory packages by relevance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/package_query.py "hedera patent"
  python scripts/package_query.py "anygrations" --top 3
  python scripts/package_query.py "sovereign ai" --fetch
  python scripts/package_query.py "patent" --category sessions
  python scripts/package_query.py --list
        """,
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Natural language query string",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Max results to return (default: 5)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Minimum relevance score 0.0-1.0 (default: 0.0 = all matches)",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        choices=list(PACKAGE_CATEGORIES.keys()),
        help="Filter results to a specific category",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch and decrypt the top result from HFS (relevance-gated load)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all packages in the index",
    )

    args = parser.parse_args()

    if not args.query and not args.list:
        parser.print_help()
        sys.exit(0)

    token_id = CONTEXT_TOKEN_ID
    key = get_package_key(token_id)

    print(f"\n[query] Loading package index from HFS...")
    index_file_id = get_package_index_file_id()
    packages = pull_package_index(index_file_id, key, token_id)
    print(f" {len(packages)} packages loaded from index {index_file_id}")

    if args.list:
        print("\n" + "=" * 70)
        print(" ALL VAULT PACKAGES")
        print("=" * 70)
        list_all_packages(packages)
        print(f"\n Total: {len(packages)} packages")
        return

    # Filter by category if specified
    search_pool = packages
    if args.category:
        search_pool = [p for p in packages if p.category == args.category]
        print(f" Filtered to category '{args.category}': {len(search_pool)} packages")

    # Query
    results = query_packages(
        query=args.query,
        packages=search_pool,
        top_n=args.top,
        threshold=args.threshold,
    )

    print(f"\n" + "=" * 70)
    print(f' QUERY: "{args.query}"')
    print(f" threshold={args.threshold} top={args.top}")
    print("=" * 70)

    if not results:
        print(" No matching packages above threshold.")
        return

    for rank, (score, pkg) in enumerate(results, 1):
        print(f"\n [{rank}] score={score:.2f} {pkg.category}/{pkg.name}")
        print(f" {pkg.description[:80]}")
        print(f" keywords: {', '.join(pkg.keywords[:6])}")
        print(f" date: {pkg.date} size: {pkg.size:,} bytes file_id: {pkg.file_id}")

    # Relevance gate: fetch all top results in parallel (only if explicitly requested)
    if args.fetch and results:
        fetch_targets = [(pkg.name, pkg.file_id) for _, pkg in results]
        print(f"\n[query] Fetching {len(fetch_targets)} package(s) from HFS in parallel...")
        fetched = pull_packages_parallel(fetch_targets, key, token_id)

        for rank, (score, pkg) in enumerate(results, 1):
            content = fetched[pkg.name]
            print(f"\n[{rank}] score={score:.2f} {pkg.category}/{pkg.name}")
            print(f" Relevance gate: score={score:.2f} >= threshold={args.threshold} -- LOAD")
            print(f" {len(content)} bytes decrypted")
            print("-" * 70)
            preview = content.decode("utf-8", errors="replace")
            print(preview[:1000])
            if len(preview) > 1000:
                print(f"\n... [{len(preview) - 1000} more chars]")
            print("-" * 70)


if __name__ == "__main__":
    main()
