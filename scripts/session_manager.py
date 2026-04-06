#!/usr/bin/env python3
"""
session_manager.py — Session State Management Utility

Manage session state for continuity across sessions.

Usage:
    python scripts/session_manager.py start "Task description" "Context summary"
    python scripts/session_manager.py end "Session summary" --duration 120
    python scripts/session_manager.py status
    python scripts/session_manager.py add-project "project-name" --priority 1
    python scripts/session_manager.py next-actions "Action 1" "Action 2" "Action 3"
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session_state import SessionState, load_session_state, save_session_state
from src.vault import VAULT_ROOT

# Session state file location
SESSION_STATE_FILE = VAULT_ROOT / "System" / "Session-State.md"


def load_state() -> SessionState:
    """Load current session state."""
    return load_session_state(SESSION_STATE_FILE)


def save_state(state: SessionState) -> None:
    """Save session state."""
    save_session_state(state, SESSION_STATE_FILE, format="markdown")
    print(f"✅ Session state saved to {SESSION_STATE_FILE}")


def cmd_start(args):
    """Start a new session."""
    state = load_state()
    state.start_session(task=args.task, context=args.context)
    save_state(state)

    print(f"\n🚀 Session Started")
    print(f"   Task: {args.task}")
    print(f"   Context: {args.context}")
    print(f"   Session #{state.metadata['session_count']}")


def cmd_end(args):
    """End current session."""
    state = load_state()
    state.end_session(
        summary=args.summary, duration_minutes=args.duration, files_modified=args.files or []
    )
    save_state(state)

    print(f"\n✅ Session Ended")
    print(f"   Summary: {args.summary}")
    print(f"   Duration: {args.duration} minutes")
    print(f"   Total sessions: {state.metadata['session_count']}")
    print(f"   Total hours: {state.metadata['total_hours']:.1f}")


def cmd_status(args):
    """Show current session status."""
    state = load_state()

    print("\n" + "=" * 60)
    print("📊 SESSION STATUS")
    print("=" * 60)
    print(f"\n📅 Current Date: {state.current_date}")
    print(f"📅 Last Session: {state.last_session_date or 'N/A'}")
    print(f"\n🎯 Current Task: {state.current_task}")
    print(f"📝 Context: {state.context_summary}")

    if state.next_actions:
        print(f"\n📋 Next Actions:")
        for i, action in enumerate(state.next_actions, 1):
            print(f"   {i}. {action}")

    if state.active_projects:
        print(f"\n📁 Active Projects:")
        for proj in state.active_projects:
            if proj.status == "active":
                priority_emoji = {1: "🔴", 2: "🟡", 3: "🟢"}.get(proj.priority, "⚪")
                print(f"   {priority_emoji} {proj.name} (updated {proj.last_updated})")

    if state.recent_sessions:
        print(f"\n📜 Recent Sessions ({len(state.recent_sessions)}):")
        for session in state.recent_sessions[-3:]:
            print(f"   • {session.date}: {session.topic}")

    print(f"\n📊 Metadata:")
    print(f"   Total Sessions: {state.metadata.get('session_count', 0)}")
    print(f"   Total Hours: {state.metadata.get('total_hours', 0):.1f}")

    print("\n" + "=" * 60)


def cmd_add_project(args):
    """Add or update a project."""
    state = load_state()
    state.add_project(
        name=args.name, status=args.status, priority=args.priority, notes=args.notes or ""
    )
    save_state(state)

    print(f"\n✅ Project '{args.name}' added/updated")
    print(f"   Status: {args.status}")
    print(f"   Priority: {args.priority}")


def cmd_next_actions(args):
    """Update next actions."""
    state = load_state()
    state.update_next_actions(args.actions)
    save_state(state)

    print(f"\n✅ Next actions updated ({len(args.actions)} items)")
    for i, action in enumerate(args.actions, 1):
        print(f"   {i}. {action}")


def cmd_continuity(args):
    """Show continuity summary for loading into new session."""
    state = load_state()
    summary = state.get_continuity_summary()

    print("\n" + "=" * 60)
    print("🔄 SESSION CONTINUITY SUMMARY")
    print("=" * 60)
    print()
    print(summary)
    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Session state management")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start a new session")
    start_parser.add_argument("task", help="Current task description")
    start_parser.add_argument("context", help="Context summary")
    start_parser.set_defaults(func=cmd_start)

    # End command
    end_parser = subparsers.add_parser("end", help="End current session")
    end_parser.add_argument("summary", help="Session summary")
    end_parser.add_argument("--duration", type=int, default=0, help="Duration in minutes")
    end_parser.add_argument("--files", nargs="*", help="Modified files")
    end_parser.set_defaults(func=cmd_end)

    # Status command
    status_parser = subparsers.add_parser("status", help="Show current status")
    status_parser.set_defaults(func=cmd_status)

    # Add project command
    project_parser = subparsers.add_parser("add-project", help="Add/update project")
    project_parser.add_argument("name", help="Project name")
    project_parser.add_argument(
        "--status", default="active", choices=["active", "paused", "completed"]
    )
    project_parser.add_argument("--priority", type=int, default=2, choices=[1, 2, 3])
    project_parser.add_argument("--notes", help="Project notes")
    project_parser.set_defaults(func=cmd_add_project)

    # Next actions command
    actions_parser = subparsers.add_parser("next-actions", help="Update next actions")
    actions_parser.add_argument("actions", nargs="+", help="List of actions")
    actions_parser.set_defaults(func=cmd_next_actions)

    # Continuity command
    continuity_parser = subparsers.add_parser("continuity", help="Show continuity summary")
    continuity_parser.set_defaults(func=cmd_continuity)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
