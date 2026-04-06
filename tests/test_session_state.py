"""
test_session_state.py — Tests for session state tracking
"""

import pytest
from datetime import date
from pathlib import Path
import tempfile
import json

from src.session_state import (
    SessionState,
    ProjectStatus,
    SessionRecord,
    load_session_state,
    save_session_state,
)


def test_create_default_session_state():
    """Test creating default session state."""
    state = SessionState.create_default()

    assert state.current_date == date.today().isoformat()
    assert state.last_session_date is None
    assert state.current_task == "No active task"
    assert state.metadata["session_count"] == 0
    assert state.metadata["total_hours"] == 0.0


def test_start_session():
    """Test starting a new session."""
    state = SessionState.create_default()

    state.start_session(
        task="Implementing session state", context="Working on sovereign-ai-context"
    )

    assert state.current_task == "Implementing session state"
    assert state.context_summary == "Working on sovereign-ai-context"
    assert state.metadata["session_count"] == 1


def test_end_session():
    """Test ending a session."""
    state = SessionState.create_default()
    state.start_session("Test task", "Test context")

    state.end_session(
        summary="Completed test implementation",
        duration_minutes=120,
        files_modified=["src/test.py", "tests/test_test.py"],
    )

    assert len(state.recent_sessions) == 1
    assert state.recent_sessions[0].topic == "Test task"
    assert state.recent_sessions[0].duration_minutes == 120
    assert state.metadata["total_hours"] == 2.0


def test_add_project():
    """Test adding projects."""
    state = SessionState.create_default()

    state.add_project(name="context-sovereignty", status="active", priority=1, notes="Main project")

    assert len(state.active_projects) == 1
    assert state.active_projects[0].name == "context-sovereignty"
    assert state.active_projects[0].priority == 1


def test_update_existing_project():
    """Test updating an existing project."""
    state = SessionState.create_default()

    state.add_project("test-project", status="active", priority=2)
    state.add_project("test-project", status="paused", priority=1)

    # Should have only 1 project (updated, not duplicated)
    assert len(state.active_projects) == 1
    assert state.active_projects[0].status == "paused"
    assert state.active_projects[0].priority == 1


def test_update_next_actions():
    """Test updating next actions."""
    state = SessionState.create_default()

    actions = ["Complete implementation", "Write tests", "Update documentation"]

    state.update_next_actions(actions)

    assert len(state.next_actions) == 3
    assert state.next_actions[0] == "Complete implementation"


def test_to_dict_and_from_dict():
    """Test serialization to/from dict."""
    state = SessionState.create_default()
    state.start_session("Test task", "Test context")
    state.add_project("test-project", status="active")
    state.update_next_actions(["Action 1", "Action 2"])

    # Convert to dict
    data = state.to_dict()

    # Convert back
    restored = SessionState.from_dict(data)

    assert restored.current_task == state.current_task
    assert len(restored.active_projects) == 1
    assert len(restored.next_actions) == 2


def test_to_markdown():
    """Test markdown generation."""
    state = SessionState.create_default()
    state.start_session("Test task", "Test context")
    state.add_project("test-project", status="active", priority=1)
    state.update_next_actions(["Action 1", "Action 2"])

    markdown = state.to_markdown()

    assert "# Session State" in markdown
    assert "Test task" in markdown
    assert "test-project" in markdown
    assert "Action 1" in markdown


def test_get_continuity_summary():
    """Test continuity summary generation."""
    state = SessionState.create_default()
    state.start_session("Implementing features", "Working on project")
    state.update_next_actions(["Complete tests", "Update docs"])
    state.add_project("main-project", status="active", priority=1)

    summary = state.get_continuity_summary()

    assert "Implementing features" in summary
    assert "Complete tests" in summary
    assert "main-project" in summary


def test_save_and_load_json():
    """Test saving and loading as JSON."""
    state = SessionState.create_default()
    state.start_session("Test task", "Test context")
    state.add_project("test-project", status="active")

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "session_state.json"

        # Save
        save_session_state(state, filepath, format="json")
        assert filepath.exists()

        # Load
        loaded = load_session_state(filepath)
        assert loaded.current_task == "Test task"
        assert len(loaded.active_projects) == 1


def test_save_and_load_markdown():
    """Test saving as markdown."""
    state = SessionState.create_default()
    state.start_session("Test task", "Test context")
    state.add_project("test-project", status="active")

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "session_state.md"

        # Save
        save_session_state(state, filepath, format="markdown")
        assert filepath.exists()

        # Verify content
        content = filepath.read_text()
        assert "# Session State" in content
        assert "Test task" in content


def test_load_nonexistent_file():
    """Test loading from nonexistent file returns default."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "nonexistent.json"

        state = load_session_state(filepath)

        assert state.current_task == "No active task"
        assert state.metadata["session_count"] == 0


def test_recent_sessions_limit():
    """Test that recent sessions are limited to 10."""
    state = SessionState.create_default()

    # Add 15 sessions
    for i in range(15):
        state.start_session(f"Task {i}", f"Context {i}")
        state.end_session(f"Summary {i}", duration_minutes=60)

    # Should keep only last 10
    assert len(state.recent_sessions) == 10
    assert state.recent_sessions[-1].summary == "Summary 14"


def test_project_status_dataclass():
    """Test ProjectStatus dataclass."""
    proj = ProjectStatus(
        name="test-project",
        status="active",
        last_updated="2026-04-01",
        priority=1,
        notes="Test notes",
    )

    assert proj.name == "test-project"
    assert proj.priority == 1


def test_session_record_dataclass():
    """Test SessionRecord dataclass."""
    record = SessionRecord(
        date="2026-04-01",
        topic="Test topic",
        summary="Test summary",
        duration_minutes=120,
        files_modified=["file1.py", "file2.py"],
    )

    assert record.date == "2026-04-01"
    assert record.duration_minutes == 120
    assert len(record.files_modified) == 2
