#!/usr/bin/env python3
"""
vault_health.py — Vault Health Check and Metadata Management

Checks vault section health, detects stale content, and manages metadata.

Usage:
    python scripts/vault_health.py                    # Show health report
    python scripts/vault_health.py --add-metadata     # Add metadata to sections without it
    python scripts/vault_health.py --mark-reviewed    # Mark all sections as reviewed today
    python scripts/vault_health.py --stale            # Show only stale sections
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vault import VAULT_ROOT, VAULT_SECTIONS, pull_section, push_section, get_section_key
from src.metadata import (
    parse_frontmatter,
    add_frontmatter,
    update_frontmatter,
    create_default_metadata,
    generate_health_report,
    get_stale_sections,
)
from src.vault_monitor import VaultMonitor, should_run_check


def load_local_sections() -> dict[str, str]:
    """Load all vault sections from local filesystem."""
    sections = {}
    for name, rel_path in VAULT_SECTIONS.items():
        path = VAULT_ROOT / rel_path
        if path.exists():
            sections[name] = path.read_text(encoding="utf-8")
        else:
            print(f"⚠️  Section '{name}' not found at {path}")
    return sections


def save_local_section(name: str, content: str) -> None:
    """Save section content to local filesystem."""
    rel_path = VAULT_SECTIONS.get(name)
    if not rel_path:
        print(f"❌ Unknown section: {name}")
        return
    
    path = VAULT_ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"✅ Saved {name} → {path}")


def show_health_report(sections: dict[str, str]) -> None:
    """Display health report."""
    report = generate_health_report(sections)
    
    print("\n" + "="*60)
    print("📊 VAULT HEALTH REPORT")
    print("="*60)
    print(f"\n📁 Total Sections: {report['total_sections']}")
    print(f"✅ With Metadata: {report['with_metadata']}")
    print(f"❌ Missing Metadata: {len(report['missing_metadata'])}")
    print(f"🟢 Active: {report['active']}")
    print(f"🟡 Stale: {report['stale']}")
    print(f"⚫ Archived: {report['archived']}")
    print(f"\n💯 Health Score: {report['health_score']}%")
    
    if report['missing_metadata']:
        print(f"\n⚠️  Sections Missing Metadata:")
        for name in report['missing_metadata']:
            print(f"   - {name}")
    
    if report['stale_sections']:
        print(f"\n🟡 Stale Sections (not reviewed in 90+ days):")
        for name, days in report['stale_sections']:
            print(f"   - {name}: {days} days ago")
    
    print("\n" + "="*60)


def show_stale_only(sections: dict[str, str]) -> None:
    """Show only stale sections."""
    stale = get_stale_sections(sections, threshold_days=90)
    
    if not stale:
        print("✅ No stale sections found!")
        return
    
    print(f"\n🟡 Found {len(stale)} stale section(s):\n")
    for name, days in stale:
        print(f"  {name:20} - {days:3} days since review")


def add_metadata_to_sections(sections: dict[str, str]) -> None:
    """Add default metadata to sections that don't have it."""
    updated = 0
    
    for name, content in sections.items():
        metadata, _ = parse_frontmatter(content)
        
        if metadata is None:
            print(f"📝 Adding metadata to {name}...")
            
            # Determine tags based on section name
            tags = ["#status/active"]
            if "soul" in name or "user" in name or "symbiote" in name:
                tags.append("#type/identity")
            elif "session" in name:
                tags.append("#type/session")
            
            default_meta = create_default_metadata(tags=tags)
            new_content = add_frontmatter(content, default_meta)
            
            save_local_section(name, new_content)
            updated += 1
    
    print(f"\n✅ Added metadata to {updated} section(s)")


def mark_all_reviewed(sections: dict[str, str]) -> None:
    """Mark all sections as reviewed today."""
    updated = 0
    
    for name, content in sections.items():
        print(f"✓ Marking {name} as reviewed...")
        new_content = update_frontmatter(content, last_reviewed=None)  # Will use today
        
        # Extract metadata to update last_reviewed properly
        from datetime import datetime
        new_content = update_frontmatter(
            content,
            last_reviewed=datetime.now().date().isoformat()
        )
        
        save_local_section(name, new_content)
        updated += 1
    
    print(f"\n✅ Marked {updated} section(s) as reviewed")


def show_monitoring_summary(sections: dict[str, str]) -> None:
    """Show automated monitoring summary."""
    from pathlib import Path
    metrics_file = Path(__file__).parent.parent / ".vault_metrics.json"
    
    monitor = VaultMonitor(metrics_file)
    
    # Run check if needed
    if should_run_check(metrics_file, interval_hours=24):
        print("🔄 Running automated health check...")
        monitor.run_health_check(sections)
    
    print("\n" + monitor.get_summary())
    
    # Show active alerts
    active_alerts = monitor.get_active_alerts()
    if active_alerts:
        print("\n⚠️  Active Alerts:")
        for alert in active_alerts[:5]:  # Show top 5
            emoji = {"critical": "🔴", "warning": "🟡", "info": "ℹ️"}.get(alert.severity, "")
            print(f"   {emoji} [{alert.severity.upper()}] {alert.message}")


def main():
    parser = argparse.ArgumentParser(description="Vault health check and metadata management")
    parser.add_argument("--add-metadata", action="store_true", help="Add metadata to sections without it")
    parser.add_argument("--mark-reviewed", action="store_true", help="Mark all sections as reviewed today")
    parser.add_argument("--stale", action="store_true", help="Show only stale sections")
    parser.add_argument("--monitor", action="store_true", help="Show automated monitoring summary")
    
    args = parser.parse_args()
    
    # Load sections
    print("📂 Loading vault sections...")
    sections = load_local_sections()
    
    if not sections:
        print("❌ No sections found!")
        return 1
    
    # Execute command
    if args.add_metadata:
        add_metadata_to_sections(sections)
    elif args.mark_reviewed:
        mark_all_reviewed(sections)
    elif args.stale:
        show_stale_only(sections)
    elif args.monitor:
        show_monitoring_summary(sections)
    else:
        show_health_report(sections)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
