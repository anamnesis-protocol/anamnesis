"""
tests/test_mcp_server.py — Unit tests for api/mcp_server.py

Tests the pure logic of each component without making real HTTP calls.
_api() is patched out in all tests so no live backend is needed.
"""

import json
from unittest.mock import patch, MagicMock, call

import pytest

import api.mcp_server as mcp_mod
from api.mcp_server import (
    update_vault_section,
    list_skills,
    save_skill_to_vault,
    _register_dynamic_skill,
    register_session_skills,
    _load_session_skills,
    _active_session,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_active_session():
    """Clear the module-level active session state between tests."""
    _active_session.clear()


@pytest.fixture(autouse=True)
def clean_session():
    _reset_active_session()
    yield
    _reset_active_session()


FAKE_SESSION_ID = "mcp-test-session"
FAKE_TOKEN_ID = "0.0.88888"


# ---------------------------------------------------------------------------
# update_vault_section — pure local state, no _api call
# ---------------------------------------------------------------------------

class TestUpdateVaultSection:
    def test_queues_update_locally(self):
        _active_session["session_id"] = FAKE_SESSION_ID
        _active_session["section_updates"] = {}

        result = update_vault_section(FAKE_SESSION_ID, "harness", "new directives")

        assert result["queued"] is True
        assert result["section_name"] == "harness"
        assert _active_session["section_updates"]["harness"] == "new directives"

    def test_wrong_session_raises(self):
        _active_session["session_id"] = "other-session"

        with pytest.raises(ValueError, match="No active session"):
            update_vault_section(FAKE_SESSION_ID, "harness", "content")

    def test_no_active_session_raises(self):
        # _active_session is empty
        with pytest.raises((ValueError, KeyError)):
            update_vault_section(FAKE_SESSION_ID, "harness", "content")

    def test_multiple_sections_queued(self):
        _active_session["session_id"] = FAKE_SESSION_ID
        _active_session["section_updates"] = {}

        update_vault_section(FAKE_SESSION_ID, "harness", "val1")
        update_vault_section(FAKE_SESSION_ID, "user", "val2")

        assert _active_session["section_updates"] == {
            "harness": "val1",
            "user": "val2",
        }


# ---------------------------------------------------------------------------
# list_skills — calls _api
# ---------------------------------------------------------------------------

class TestListSkills:
    def test_returns_skills_from_api(self):
        api_response = {
            "token_id": FAKE_TOKEN_ID,
            "skills": [
                {"id": "s1", "name": "my_skill", "description": "does X", "tags": [], "version": "1.0.0"},
            ],
        }
        with patch("api.mcp_server._api", return_value=api_response):
            result = list_skills(FAKE_SESSION_ID)

        assert result["count"] == 1
        assert result["skills"][0]["name"] == "my_skill"
        assert result["token_id"] == FAKE_TOKEN_ID

    def test_empty_vault_returns_zero_count(self):
        with patch("api.mcp_server._api", return_value={"token_id": FAKE_TOKEN_ID, "skills": []}):
            result = list_skills(FAKE_SESSION_ID)
        assert result["count"] == 0

    def test_api_called_with_correct_params(self):
        with patch("api.mcp_server._api", return_value={"skills": []}) as mock_api:
            list_skills(FAKE_SESSION_ID)
        mock_api.assert_called_once_with(
            "get", "/skills", params={"session_id": FAKE_SESSION_ID}
        )


# ---------------------------------------------------------------------------
# save_skill_to_vault — JSON parsing + _api call
# ---------------------------------------------------------------------------

class TestSaveSkillToVault:
    def test_valid_json_schema_parsed(self):
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        api_response = {"skill_id": "s1", "name": "test", "version": "1.0.0", "message": "created"}
        with patch("api.mcp_server._api", return_value=api_response) as mock_api:
            save_skill_to_vault(
                session_id=FAKE_SESSION_ID,
                name="test_skill",
                description="does test",
                instructions="step 1",
                input_schema=json.dumps(schema),
            )
        payload = mock_api.call_args[1]["json"]
        assert payload["input_schema"] == schema

    def test_invalid_json_schema_falls_back_to_empty(self):
        api_response = {"skill_id": "s1", "name": "test", "version": "1.0.0", "message": "created"}
        with patch("api.mcp_server._api", return_value=api_response) as mock_api:
            save_skill_to_vault(
                session_id=FAKE_SESSION_ID,
                name="test_skill",
                description="desc",
                instructions="step 1",
                input_schema="not valid json {{{",
            )
        payload = mock_api.call_args[1]["json"]
        assert payload["input_schema"] == {"type": "object", "properties": {}}

    def test_tags_string_split_into_list(self):
        api_response = {"skill_id": "s1", "name": "test", "version": "1.0.0", "message": "created"}
        with patch("api.mcp_server._api", return_value=api_response) as mock_api:
            save_skill_to_vault(
                session_id=FAKE_SESSION_ID,
                name="tagged_skill",
                description="desc",
                instructions="step 1",
                input_schema="{}",
                tags="security, audit, hedera",
            )
        payload = mock_api.call_args[1]["json"]
        assert payload["tags"] == ["security", "audit", "hedera"]

    def test_empty_tags_string_gives_empty_list(self):
        api_response = {"skill_id": "s1", "name": "test", "version": "1.0.0", "message": "created"}
        with patch("api.mcp_server._api", return_value=api_response) as mock_api:
            save_skill_to_vault(
                session_id=FAKE_SESSION_ID,
                name="no_tags",
                description="desc",
                instructions="step 1",
                input_schema="{}",
                tags="",
            )
        payload = mock_api.call_args[1]["json"]
        assert payload["tags"] == []

    def test_skill_id_included_when_provided(self):
        api_response = {"skill_id": "existing-id", "name": "test", "version": "1.0.1", "message": "updated"}
        with patch("api.mcp_server._api", return_value=api_response) as mock_api:
            save_skill_to_vault(
                session_id=FAKE_SESSION_ID,
                name="update_me",
                description="desc",
                instructions="step 1",
                input_schema="{}",
                skill_id="existing-id",
            )
        payload = mock_api.call_args[1]["json"]
        assert payload["skill_id"] == "existing-id"

    def test_skill_id_omitted_when_empty(self):
        api_response = {"skill_id": "new-id", "name": "test", "version": "1.0.0", "message": "created"}
        with patch("api.mcp_server._api", return_value=api_response) as mock_api:
            save_skill_to_vault(
                session_id=FAKE_SESSION_ID,
                name="new_skill",
                description="desc",
                instructions="step 1",
                input_schema="{}",
                skill_id="",
            )
        payload = mock_api.call_args[1]["json"]
        assert "skill_id" not in payload


# ---------------------------------------------------------------------------
# _load_session_skills
# ---------------------------------------------------------------------------

class TestLoadSessionSkills:
    def test_returns_tools_list(self):
        tools = [{"name": "skill_a", "description": "does a", "_instructions": "step 1"}]
        with patch("api.mcp_server._api", return_value={"tools": tools}):
            result = _load_session_skills(FAKE_SESSION_ID)
        assert result == tools

    def test_api_failure_returns_empty_list(self):
        with patch("api.mcp_server._api", side_effect=RuntimeError("backend down")):
            result = _load_session_skills(FAKE_SESSION_ID)
        assert result == []

    def test_empty_tools_returns_empty_list(self):
        with patch("api.mcp_server._api", return_value={"tools": []}):
            result = _load_session_skills(FAKE_SESSION_ID)
        assert result == []


# ---------------------------------------------------------------------------
# _register_dynamic_skill
# ---------------------------------------------------------------------------

class TestRegisterDynamicSkill:
    def test_handler_returns_correct_shape(self):
        tool_def = {
            "name": "my_skill",
            "description": "does my thing",
            "_instructions": "step 1: do X",
            "inputSchema": {"type": "object", "properties": {}},
        }
        # Capture the handler before it's registered with FastMCP
        captured_handler = None

        original_tool = mcp_mod.mcp.tool

        def _capture_tool(name=None):
            def _decorator(fn):
                nonlocal captured_handler
                captured_handler = fn
                return fn
            return _decorator

        with patch.object(mcp_mod.mcp, "tool", side_effect=_capture_tool):
            _register_dynamic_skill(tool_def)

        assert captured_handler is not None
        result = captured_handler(code="test contract")
        assert result["skill"] == "my_skill"
        assert result["instructions"] == "step 1: do X"
        assert result["inputs"] == {"code": "test contract"}
        assert "message" in result

    def test_handler_name_set_to_skill_name(self):
        tool_def = {
            "name": "audit_abi",
            "description": "audits an ABI",
            "_instructions": "analyze it",
            "inputSchema": {},
        }
        captured_fn = None

        def _capture_tool(name=None):
            def _decorator(fn):
                nonlocal captured_fn
                captured_fn = fn
                return fn
            return _decorator

        with patch.object(mcp_mod.mcp, "tool", side_effect=_capture_tool):
            _register_dynamic_skill(tool_def)

        assert captured_fn.__name__ == "audit_abi"

    def test_handler_docstring_is_description(self):
        tool_def = {
            "name": "check_abi",
            "description": "Checks the ABI for issues",
            "_instructions": "look for missing functions",
            "inputSchema": {},
        }
        captured_fn = None

        def _capture_tool(name=None):
            def _decorator(fn):
                nonlocal captured_fn
                captured_fn = fn
                return fn
            return _decorator

        with patch.object(mcp_mod.mcp, "tool", side_effect=_capture_tool):
            _register_dynamic_skill(tool_def)

        assert captured_fn.__doc__ == "Checks the ABI for issues"


# ---------------------------------------------------------------------------
# register_session_skills
# ---------------------------------------------------------------------------

class TestRegisterSessionSkills:
    def test_returns_count_of_loaded_skills(self):
        tools = [
            {"name": "skill_a", "_instructions": "a", "description": "A", "inputSchema": {}},
            {"name": "skill_b", "_instructions": "b", "description": "B", "inputSchema": {}},
        ]
        with patch("api.mcp_server._load_session_skills", return_value=tools), \
             patch("api.mcp_server._register_dynamic_skill") as mock_reg:
            count = register_session_skills(FAKE_SESSION_ID)

        assert count == 2
        assert mock_reg.call_count == 2

    def test_bad_skill_skipped_does_not_raise(self):
        tools = [
            {"name": "good_skill", "_instructions": "ok", "description": "ok", "inputSchema": {}},
            {"name": "bad_skill", "_instructions": "fail", "description": "fail", "inputSchema": {}},
        ]

        def _register_with_failure(tool_def):
            if tool_def["name"] == "bad_skill":
                raise RuntimeError("registration failed")

        with patch("api.mcp_server._load_session_skills", return_value=tools), \
             patch("api.mcp_server._register_dynamic_skill", side_effect=_register_with_failure):
            count = register_session_skills(FAKE_SESSION_ID)  # should not raise

        assert count == 2  # both attempted; count is total not successful

    def test_empty_tools_returns_zero(self):
        with patch("api.mcp_server._load_session_skills", return_value=[]):
            count = register_session_skills(FAKE_SESSION_ID)
        assert count == 0
