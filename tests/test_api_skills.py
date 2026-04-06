"""
tests/test_api_skills.py — HTTP endpoint tests for /skills routes.

get_session is mocked so no live HFS/HCS needed.
skill_packages functions are mocked so crypto + HFS I/O is bypassed.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SOVEREIGN_ENV", "testnet")
os.environ.setdefault("HEDERA_NETWORK", "testnet")
os.environ.setdefault("OPERATOR_ID", "0.0.1234")
os.environ.setdefault("OPERATOR_KEY", "302e020100300506032b657004220420" + "a" * 64)

from api.main import app  # noqa: E402
from src.skill_packages import SkillMetadata, SkillPackage  # noqa: E402

client = TestClient(app)

SESSION_ID = "test-skills-session"
TOKEN_ID = "0.0.55555"
FAKE_FILE_ID = "0.0.100001"


def _mock_session():
    s = MagicMock()
    s.session_id = SESSION_ID
    s.token_id = TOKEN_ID
    s.expired = False
    return s


def _make_meta(**kwargs) -> SkillMetadata:
    defaults = dict(
        id="skill-001",
        name="analyze_contract",
        description="Analyzes a smart contract",
        tags=["solidity", "security"],
        file_id=FAKE_FILE_ID,
        version="1.0.0",
        created_at="2026-04-01T00:00:00Z",
    )
    defaults.update(kwargs)
    return SkillMetadata(**defaults)


def _make_package(**kwargs) -> SkillPackage:
    defaults = dict(
        id="skill-001",
        name="analyze_contract",
        description="Analyzes a smart contract",
        version="1.0.0",
        created_at="2026-04-01T00:00:00Z",
        updated_at="2026-04-01T00:00:00Z",
        tags=["solidity", "security"],
        input_schema={"type": "object", "properties": {"code": {"type": "string"}}},
        instructions="Step 1: read code. Step 2: check for bugs.",
        examples=[],
    )
    defaults.update(kwargs)
    return SkillPackage(**defaults)


# ---------------------------------------------------------------------------
# GET /skills
# ---------------------------------------------------------------------------


class TestListSkills:
    def test_missing_session_returns_404(self):
        with patch("api.routes.skills.get_session", return_value=None):
            resp = client.get("/skills", params={"session_id": "bad-session"})
        assert resp.status_code == 404

    def test_empty_vault_returns_empty_list(self):
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.query_skills", return_value=[]),
        ):
            resp = client.get("/skills", params={"session_id": SESSION_ID})
        assert resp.status_code == 200
        data = resp.json()
        assert data["skills"] == []
        assert data["token_id"] == TOKEN_ID

    def test_returns_skills_list(self):
        metas = [_make_meta(), _make_meta(id="skill-002", name="another_skill")]
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.query_skills", return_value=metas),
        ):
            resp = client.get("/skills", params={"session_id": SESSION_ID})
        assert resp.status_code == 200
        assert len(resp.json()["skills"]) == 2

    def test_tag_filter_forwarded(self):
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()) as _,
            patch("api.routes.skills.query_skills", return_value=[]) as mock_query,
        ):
            client.get("/skills", params={"session_id": SESSION_ID, "tags": "security,audit"})
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args[1]
        assert call_kwargs["tags"] == ["security", "audit"]

    def test_name_contains_filter_forwarded(self):
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.query_skills", return_value=[]) as mock_query,
        ):
            client.get("/skills", params={"session_id": SESSION_ID, "name_contains": "contract"})
        call_kwargs = mock_query.call_args[1]
        assert call_kwargs["name_contains"] == "contract"

    def test_skill_summary_shape(self):
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.query_skills", return_value=[_make_meta()]),
        ):
            resp = client.get("/skills", params={"session_id": SESSION_ID})
        skill = resp.json()["skills"][0]
        for key in ("id", "name", "description", "tags", "version", "created_at"):
            assert key in skill


# ---------------------------------------------------------------------------
# GET /skills/tools
# ---------------------------------------------------------------------------


class TestListSkillTools:
    def test_missing_session_returns_404(self):
        with patch("api.routes.skills.get_session", return_value=None):
            resp = client.get("/skills/tools", params={"session_id": "bad"})
        assert resp.status_code == 404

    def test_returns_mcp_tool_definitions(self):
        package = _make_package()
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.query_skills", return_value=[_make_meta()]),
            patch("api.routes.skills.pull_skill", return_value=package),
        ):
            resp = client.get("/skills/tools", params={"session_id": SESSION_ID})
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "analyze_contract"
        assert "_instructions" in tools[0]
        assert "inputSchema" in tools[0]

    def test_failed_pull_skipped_not_500(self):
        """If a skill fails to load from HFS, skip it rather than 500."""
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.query_skills", return_value=[_make_meta()]),
            patch("api.routes.skills.pull_skill", side_effect=RuntimeError("HFS down")),
        ):
            resp = client.get("/skills/tools", params={"session_id": SESSION_ID})
        assert resp.status_code == 200
        assert resp.json()["tools"] == []


# ---------------------------------------------------------------------------
# GET /skills/{skill_id}
# ---------------------------------------------------------------------------


class TestGetSkill:
    def test_missing_session_returns_404(self):
        with patch("api.routes.skills.get_session", return_value=None):
            resp = client.get("/skills/skill-001", params={"session_id": "bad"})
        assert resp.status_code == 404

    def test_skill_not_in_index_returns_404(self):
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.query_skills", return_value=[]),
        ):
            resp = client.get("/skills/skill-001", params={"session_id": SESSION_ID})
        assert resp.status_code == 404

    def test_returns_full_skill_detail(self):
        package = _make_package()
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.query_skills", return_value=[_make_meta()]),
            patch("api.routes.skills.pull_skill", return_value=package),
        ):
            resp = client.get("/skills/skill-001", params={"session_id": SESSION_ID})
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "skill-001"
        assert data["instructions"] == package.instructions
        assert "input_schema" in data
        assert "examples" in data

    def test_hfs_failure_returns_502(self):
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.query_skills", return_value=[_make_meta()]),
            patch("api.routes.skills.pull_skill", side_effect=RuntimeError("network error")),
        ):
            resp = client.get("/skills/skill-001", params={"session_id": SESSION_ID})
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# POST /skills
# ---------------------------------------------------------------------------


class TestUpsertSkill:
    def test_missing_session_returns_404(self):
        with patch("api.routes.skills.get_session", return_value=None):
            resp = client.post(
                "/skills",
                params={"session_id": "bad"},
                json={"name": "x", "description": "y", "instructions": "z"},
            )
        assert resp.status_code == 404

    def test_create_new_skill_returns_200(self):
        package = _make_package()
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.save_skill", return_value=package),
        ):
            resp = client.post(
                "/skills",
                params={"session_id": SESSION_ID},
                json={
                    "name": "analyze_contract",
                    "description": "Analyzes a contract",
                    "instructions": "Step 1...",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skill_id"] == "skill-001"
        assert "created" in data["message"]

    def test_update_existing_skill_message_says_updated(self):
        package = _make_package()
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.save_skill", return_value=package),
        ):
            resp = client.post(
                "/skills",
                params={"session_id": SESSION_ID},
                json={
                    "name": "analyze_contract",
                    "description": "Updated",
                    "instructions": "New steps",
                    "skill_id": "skill-001",
                },
            )
        assert resp.status_code == 200
        assert "updated" in resp.json()["message"]

    def test_save_failure_returns_502(self):
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.save_skill", side_effect=RuntimeError("HFS write failed")),
        ):
            resp = client.post(
                "/skills",
                params={"session_id": SESSION_ID},
                json={"name": "x", "description": "y", "instructions": "z"},
            )
        assert resp.status_code == 502

    def test_save_skill_called_with_correct_token_id(self):
        package = _make_package()
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.save_skill", return_value=package) as mock_save,
        ):
            client.post(
                "/skills",
                params={"session_id": SESSION_ID},
                json={"name": "x", "description": "y", "instructions": "z"},
            )
        assert mock_save.call_args[1]["token_id"] == TOKEN_ID


# ---------------------------------------------------------------------------
# DELETE /skills/{skill_id}
# ---------------------------------------------------------------------------


class TestDeleteSkillEndpoint:
    def test_missing_session_returns_404(self):
        with patch("api.routes.skills.get_session", return_value=None):
            resp = client.delete("/skills/skill-001", params={"session_id": "bad"})
        assert resp.status_code == 404

    def test_delete_existing_returns_deleted_true(self):
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.delete_skill", return_value=True),
        ):
            resp = client.delete("/skills/skill-001", params={"session_id": SESSION_ID})
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["skill_id"] == "skill-001"

    def test_delete_nonexistent_returns_deleted_false(self):
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.delete_skill", return_value=False),
        ):
            resp = client.delete("/skills/ghost-id", params={"session_id": SESSION_ID})
        assert resp.status_code == 200
        assert resp.json()["deleted"] is False

    def test_index_failure_returns_502(self):
        with (
            patch("api.routes.skills.get_session", return_value=_mock_session()),
            patch("api.routes.skills.delete_skill", side_effect=RuntimeError("index corrupt")),
        ):
            resp = client.delete("/skills/skill-001", params={"session_id": SESSION_ID})
        assert resp.status_code == 502
