"""
session_state.py — Session State Tracking and Persistence

Implements session state management inspired by Symbiosis vault architecture.
Tracks current work, context, and continuity across sessions.

Session State Schema:
{
    "current_date": "2026-04-01",
    "last_session_date": "2026-03-31",
    "current_task": "Implementing session state tracking",
    "context_summary": "Working on sovereign-ai-context repository improvements",
    "next_actions": [
        "Complete session state implementation",
        "Test session continuity",
        "Document usage"
    ],
    "active_projects": [
        {"name": "context-sovereignty", "status": "active", "last_updated": "2026-04-01"}
    ],
    "recent_sessions": [
        {
            "date": "2026-03-31",
            "topic": "RAG implementation",
            "summary": "Implemented TF-IDF RAG for memory packages",
            "duration_minutes": 120
        }
    ],
    "metadata": {
        "session_count": 42,
        "total_hours": 84.5,
        "last_reviewed": "2026-04-01"
    }
}
"""

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, date
from typing import Optional, List
from pathlib import Path


@dataclass
class ProjectStatus:
    """Status of an active project."""
    name: str
    status: str  # active | paused | completed
    last_updated: str  # ISO date
    priority: int = 2  # 1=high, 2=medium, 3=low
    notes: str = ""


@dataclass
class SessionRecord:
    """Record of a past session."""
    date: str  # ISO date
    topic: str
    summary: str
    duration_minutes: int = 0
    files_modified: List[str] = field(default_factory=list)


@dataclass
class SessionState:
    """Complete session state."""
    current_date: str
    last_session_date: Optional[str]
    current_task: str
    context_summary: str
    next_actions: List[str]
    active_projects: List[ProjectStatus]
    recent_sessions: List[SessionRecord]
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "current_date": self.current_date,
            "last_session_date": self.last_session_date,
            "current_task": self.current_task,
            "context_summary": self.context_summary,
            "next_actions": self.next_actions,
            "active_projects": [asdict(p) for p in self.active_projects],
            "recent_sessions": [asdict(s) for s in self.recent_sessions],
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        """Create from dict (JSON deserialization)."""
        return cls(
            current_date=data["current_date"],
            last_session_date=data.get("last_session_date"),
            current_task=data["current_task"],
            context_summary=data["context_summary"],
            next_actions=data.get("next_actions", []),
            active_projects=[
                ProjectStatus(**p) for p in data.get("active_projects", [])
            ],
            recent_sessions=[
                SessionRecord(**s) for s in data.get("recent_sessions", [])
            ],
            metadata=data.get("metadata", {}),
        )
    
    def to_markdown(self) -> str:
        """
        Convert to markdown format for vault storage.
        
        Returns:
            Markdown-formatted session state
        """
        lines = [
            "# Session State",
            "",
            f"**Last Updated:** {self.current_date}",
            f"**Last Session:** {self.last_session_date or 'N/A'}",
            "",
            "## Current Work",
            "",
            f"**Task:** {self.current_task}",
            "",
            f"**Context:** {self.context_summary}",
            "",
            "## Next Actions",
            "",
        ]
        
        for i, action in enumerate(self.next_actions, 1):
            lines.append(f"{i}. {action}")
        
        lines.extend([
            "",
            "## Active Projects",
            "",
        ])
        
        for proj in self.active_projects:
            priority_emoji = {1: "🔴", 2: "🟡", 3: "🟢"}.get(proj.priority, "⚪")
            status_emoji = {
                "active": "✅",
                "paused": "⏸️",
                "completed": "✔️"
            }.get(proj.status, "❓")
            
            lines.append(f"### {status_emoji} {proj.name} {priority_emoji}")
            lines.append(f"- **Status:** {proj.status}")
            lines.append(f"- **Last Updated:** {proj.last_updated}")
            if proj.notes:
                lines.append(f"- **Notes:** {proj.notes}")
            lines.append("")
        
        lines.extend([
            "## Recent Sessions",
            "",
        ])
        
        for session in self.recent_sessions[-5:]:  # Last 5 sessions
            lines.append(f"### {session.date} - {session.topic}")
            lines.append(f"{session.summary}")
            if session.duration_minutes:
                lines.append(f"*Duration: {session.duration_minutes} minutes*")
            lines.append("")
        
        lines.extend([
            "## Metadata",
            "",
            f"- **Total Sessions:** {self.metadata.get('session_count', 0)}",
            f"- **Total Hours:** {self.metadata.get('total_hours', 0):.1f}",
            f"- **Last Reviewed:** {self.metadata.get('last_reviewed', 'N/A')}",
        ])
        
        return "\n".join(lines)
    
    @classmethod
    def from_markdown(cls, content: str) -> "SessionState":
        """
        Parse session state from markdown format.
        
        This is a simplified parser - for production use, consider
        a more robust markdown parser.
        
        Args:
            content: Markdown content
            
        Returns:
            SessionState instance
        """
        # For now, return a default state
        # Full markdown parsing would be complex
        return cls.create_default()
    
    @classmethod
    def create_default(cls) -> "SessionState":
        """Create default session state."""
        today = date.today().isoformat()
        return cls(
            current_date=today,
            last_session_date=None,
            current_task="No active task",
            context_summary="New session",
            next_actions=[],
            active_projects=[],
            recent_sessions=[],
            metadata={
                "session_count": 0,
                "total_hours": 0.0,
                "last_reviewed": today,
            },
        )
    
    def start_session(self, task: str, context: str) -> None:
        """
        Start a new session.
        
        Args:
            task: Current task description
            context: Context summary
        """
        self.last_session_date = self.current_date
        self.current_date = date.today().isoformat()
        self.current_task = task
        self.context_summary = context
        self.metadata["session_count"] = self.metadata.get("session_count", 0) + 1
    
    def end_session(
        self,
        summary: str,
        duration_minutes: int = 0,
        files_modified: Optional[List[str]] = None
    ) -> None:
        """
        End current session and archive it.
        
        Args:
            summary: Session summary
            duration_minutes: Session duration
            files_modified: List of modified files
        """
        session_record = SessionRecord(
            date=self.current_date,
            topic=self.current_task,
            summary=summary,
            duration_minutes=duration_minutes,
            files_modified=files_modified or [],
        )
        
        self.recent_sessions.append(session_record)
        
        # Keep only last 10 sessions
        if len(self.recent_sessions) > 10:
            self.recent_sessions = self.recent_sessions[-10:]
        
        # Update total hours
        hours = duration_minutes / 60.0
        self.metadata["total_hours"] = self.metadata.get("total_hours", 0.0) + hours
    
    def add_project(
        self,
        name: str,
        status: str = "active",
        priority: int = 2,
        notes: str = ""
    ) -> None:
        """Add or update a project."""
        # Check if project exists
        for proj in self.active_projects:
            if proj.name == name:
                proj.status = status
                proj.priority = priority
                proj.last_updated = date.today().isoformat()
                if notes:
                    proj.notes = notes
                return
        
        # Add new project
        self.active_projects.append(
            ProjectStatus(
                name=name,
                status=status,
                last_updated=date.today().isoformat(),
                priority=priority,
                notes=notes,
            )
        )
    
    def update_next_actions(self, actions: List[str]) -> None:
        """Update next actions list."""
        self.next_actions = actions
    
    def get_continuity_summary(self) -> str:
        """
        Get a summary for session continuity.
        
        Returns:
            Summary string for loading into new session
        """
        lines = [
            f"Last session: {self.last_session_date or 'N/A'}",
            f"Current task: {self.current_task}",
            f"Context: {self.context_summary}",
            "",
            "Next actions:",
        ]
        
        for action in self.next_actions:
            lines.append(f"  - {action}")
        
        if self.active_projects:
            lines.append("")
            lines.append("Active projects:")
            for proj in self.active_projects:
                if proj.status == "active":
                    lines.append(f"  - {proj.name} (priority {proj.priority})")
        
        return "\n".join(lines)


def load_session_state(filepath: Path) -> SessionState:
    """
    Load session state from file.
    
    Args:
        filepath: Path to session state file (JSON or markdown)
        
    Returns:
        SessionState instance
    """
    if not filepath.exists():
        return SessionState.create_default()
    
    content = filepath.read_text(encoding="utf-8")
    
    # Try JSON first
    if filepath.suffix == ".json":
        data = json.loads(content)
        return SessionState.from_dict(data)
    
    # Try markdown
    return SessionState.from_markdown(content)


def save_session_state(state: SessionState, filepath: Path, format: str = "markdown") -> None:
    """
    Save session state to file.
    
    Args:
        state: SessionState to save
        filepath: Output file path
        format: "json" or "markdown"
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    if format == "json":
        content = json.dumps(state.to_dict(), indent=2, ensure_ascii=False)
    else:  # markdown
        content = state.to_markdown()
    
    filepath.write_text(content, encoding="utf-8")
