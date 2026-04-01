#!/usr/bin/env python3
"""
context_manager.py — Bounded Context Management Utility

Manage bounded contexts for memory packages.

Usage:
    python scripts/context_manager.py list                    # List all contexts
    python scripts/context_manager.py suggest PACKAGE_NAME    # Suggest contexts
    python scripts/context_manager.py stats                   # Show statistics
    python scripts/context_manager.py assign PACKAGE_NAME CONTEXT  # Assign context
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bounded_contexts import (
    BoundedContext,
    ContextMapping,
    suggest_context_for_package,
    get_context_summary,
)


def cmd_list(args):
    """List all available bounded contexts."""
    print("\n" + "="*60)
    print("📚 AVAILABLE BOUNDED CONTEXTS")
    print("="*60)
    
    for context in BoundedContext:
        if context == BoundedContext.GENERAL:
            continue
        
        print(f"\n🏷️  {context.value}")
        print(f"   {context.get_description()}")
        
        keywords = context.get_keywords()
        if keywords:
            keyword_list = sorted(list(keywords))[:10]  # Show first 10
            print(f"   Keywords: {', '.join(keyword_list)}")
            if len(keywords) > 10:
                print(f"   ... and {len(keywords) - 10} more")
    
    print("\n" + "="*60)


def cmd_suggest(args):
    """Suggest contexts for a package."""
    # For demo, use provided keywords or defaults
    keywords = args.keywords if args.keywords else []
    description = args.description if args.description else ""
    
    mapping = suggest_context_for_package(
        args.package_name,
        keywords,
        description
    )
    
    print(f"\n📦 Package: {args.package_name}")
    print(f"🎯 Suggested Contexts (confidence: {mapping.confidence:.1%}):")
    
    for context in mapping.contexts:
        print(f"   • {context.value}: {context.get_description()}")
    
    print()


def cmd_stats(args):
    """Show context statistics."""
    # This would load from actual package index in production
    # For now, show example
    print("\n" + "="*60)
    print("📊 BOUNDED CONTEXT STATISTICS")
    print("="*60)
    print("\nNote: This is a demo. In production, this would analyze")
    print("your actual package index.")
    print("\nExample distribution:")
    
    example_mappings = {
        "pkg1": ContextMapping("pkg1", [BoundedContext.AI_ENGINEERING]),
        "pkg2": ContextMapping("pkg2", [BoundedContext.HEDERA]),
        "pkg3": ContextMapping("pkg3", [BoundedContext.PYTHON]),
        "pkg4": ContextMapping("pkg4", [BoundedContext.AI_ENGINEERING]),
    }
    
    summary = get_context_summary(example_mappings)
    
    print(f"\nTotal Packages: {summary['total_packages']}")
    print("\nContext Distribution:")
    
    for context_name, stats in summary['context_distribution'].items():
        print(f"  {context_name:20} {stats['count']:3} ({stats['percentage']:5.1f}%)")
        print(f"    {stats['description']}")
    
    print("\n" + "="*60)


def cmd_assign(args):
    """Assign context to a package."""
    try:
        context = BoundedContext.from_string(args.context)
        print(f"\n✅ Would assign context '{context.value}' to package '{args.package_name}'")
        print(f"   {context.get_description()}")
        print("\nNote: This is a demo. In production, this would update")
        print("the package index with the new context assignment.")
    except ValueError:
        print(f"\n❌ Invalid context: {args.context}")
        print("Use 'list' command to see available contexts.")


def main():
    parser = argparse.ArgumentParser(description="Bounded context management")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all bounded contexts")
    list_parser.set_defaults(func=cmd_list)
    
    # Suggest command
    suggest_parser = subparsers.add_parser("suggest", help="Suggest contexts for a package")
    suggest_parser.add_argument("package_name", help="Package name")
    suggest_parser.add_argument("--keywords", nargs="*", help="Package keywords")
    suggest_parser.add_argument("--description", help="Package description")
    suggest_parser.set_defaults(func=cmd_suggest)
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show context statistics")
    stats_parser.set_defaults(func=cmd_stats)
    
    # Assign command
    assign_parser = subparsers.add_parser("assign", help="Assign context to package")
    assign_parser.add_argument("package_name", help="Package name")
    assign_parser.add_argument("context", help="Context name")
    assign_parser.set_defaults(func=cmd_assign)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
