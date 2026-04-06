"""
tests/test_skill_packages.py — Unit tests for src/skill_packages.py

All HFS I/O (store_context, load_context, update_context), crypto key
derivation (get_package_key), and local index I/O (load/save_local_index)
are mocked so tests run offline.
"""

import json
from dataclasses import asdict
from unittest.mock import MagicMock, patch, call
import pytest

from src.skill_packages import (
    SkillPackage,
    SkillMetadata,
    query_skills,
    save_skill,
    delete_skill,
    push_skill_index,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FAKE_TOKEN = "0.0.55555"
FAKE_KEY = b"\x01" * 32
FAKE_FILE_ID = "0.0.100001"
FAKE_INDEX_FILE_ID = "0.0.100002"

SKILL_ENTRY = {
    "id": "skill-001",
    "name": "analyze_contract",
    "description": "Analyzes a contract",
    "tags": ["solidity", "security"],
    "file_id": FAKE_FILE_ID,
    "version": "1.0.0",
    "created_at": "2026-04-01T00:00:00Z",
}

FULL_INDEX = {
    "version": "1.0",
    "last_updated": "2026-04-01",
    "skills": [SKILL_ENTRY],
}


def _make_skill(**kwargs) -> SkillPackage:
    defaults = dict(
        id="skill-001",
        name="analyze_contract",
        description="Analyzes a contract",
        version="1.0.0",
        created_at="2026-04-01T00:00:00Z",
        updated_at="2026-04-01T00:00:00Z",
        tags=["solidity", "security"],
        input_schema={"type": "object", "properties": {"code": {"type": "string"}}},
        instructions="Step 1: read the code. Step 2: check for reentrancy.",
        examples=[{"input": {"code": "..."}, "output": "clean"}],
    )
    defaults.update(kwargs)
    return SkillPackage(**defaults)


# ---------------------------------------------------------------------------
# SkillPackage dataclass
# ---------------------------------------------------------------------------


class TestSkillPackage:
    def test_to_mcp_tool_required_keys(self):
        skill = _make_skill()
        tool = skill.to_mcp_tool()
        assert tool["name"] == "analyze_contract"
        assert tool["description"] == "Analyzes a contract"
        assert "inputSchema" in tool
        assert "_skill_id" in tool
        assert "_instructions" in tool

    def test_to_mcp_tool_passes_input_schema(self):
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        skill = _make_skill(input_schema=schema)
        assert skill.to_mcp_tool()["inputSchema"] == schema

    def test_to_mcp_tool_passes_instructions(self):
        skill = _make_skill(instructions="do X then Y")
        assert skill.to_mcp_tool()["_instructions"] == "do X then Y"

    def test_from_dict_minimal(self):
        data = {"id": "abc", "name": "my_skill", "description": "does things"}
        skill = SkillPackage.from_dict(data)
        assert skill.id == "abc"
        assert skill.name == "my_skill"
        assert skill.version == "1.0.0"
        assert skill.tags == []
        assert skill.examples == []
        assert skill.input_schema == {"type": "object", "properties": {}}

    def test_from_dict_full(self):
        data = asdict(_make_skill())
        skill = SkillPackage.from_dict(data)
        assert skill.id == "skill-001"
        assert skill.tags == ["solidity", "security"]
        assert skill.examples == [{"input": {"code": "..."}, "output": "clean"}]

    def test_from_dict_roundtrip(self):
        original = _make_skill()
        restored = SkillPackage.from_dict(asdict(original))
        assert asdict(original) == asdict(restored)


# ---------------------------------------------------------------------------
# query_skills — mocks _load_skill_index
# ---------------------------------------------------------------------------


class TestQuerySkills:
    def _patch_index(self, index_data: dict):
        return patch("src.skill_packages._load_skill_index", return_value=index_data)

    def test_returns_all_with_no_filter(self):
        with self._patch_index(FULL_INDEX):
            results = query_skills(FAKE_TOKEN)
        assert len(results) == 1
        assert results[0].id == "skill-001"
        assert results[0].name == "analyze_contract"

    def test_empty_index_returns_empty_list(self):
        empty = {"version": "1.0", "last_updated": "", "skills": []}
        with self._patch_index(empty):
            results = query_skills(FAKE_TOKEN)
        assert results == []

    def test_tag_filter_matches(self):
        with self._patch_index(FULL_INDEX):
            results = query_skills(FAKE_TOKEN, tags=["security"])
        assert len(results) == 1

    def test_tag_filter_no_match(self):
        with self._patch_index(FULL_INDEX):
            results = query_skills(FAKE_TOKEN, tags=["nonexistent"])
        assert results == []

    def test_tag_filter_case_insensitive(self):
        with self._patch_index(FULL_INDEX):
            results = query_skills(FAKE_TOKEN, tags=["SECURITY"])
        assert len(results) == 1

    def test_name_contains_matches(self):
        with self._patch_index(FULL_INDEX):
            results = query_skills(FAKE_TOKEN, name_contains="contract")
        assert len(results) == 1

    def test_name_contains_no_match(self):
        with self._patch_index(FULL_INDEX):
            results = query_skills(FAKE_TOKEN, name_contains="nonexistent")
        assert results == []

    def test_name_contains_case_insensitive(self):
        with self._patch_index(FULL_INDEX):
            results = query_skills(FAKE_TOKEN, name_contains="CONTRACT")
        assert len(results) == 1

    def test_limit_respected(self):
        many_skills = [{**SKILL_ENTRY, "id": f"skill-{i}", "name": f"skill_{i}"} for i in range(10)]
        index = {**FULL_INDEX, "skills": many_skills}
        with self._patch_index(index):
            results = query_skills(FAKE_TOKEN, limit=3)
        assert len(results) == 3

    def test_returns_correct_metadata_type(self):
        with self._patch_index(FULL_INDEX):
            results = query_skills(FAKE_TOKEN)
        assert isinstance(results[0], SkillMetadata)
        assert results[0].file_id == FAKE_FILE_ID


# ---------------------------------------------------------------------------
# save_skill — mocks all HFS + index I/O
# ---------------------------------------------------------------------------

IO_PATCHES = [
    "src.skill_packages.get_package_key",
    "src.skill_packages.store_context",
    "src.skill_packages.update_context",
    "src.skill_packages.load_context",
    "src.skill_packages.load_local_index",
    "src.skill_packages.save_local_index",
    "src.skill_packages.log_event",
]


@pytest.fixture
def mock_io():
    """Patch all HFS + index I/O for skill_packages."""
    with (
        patch("src.skill_packages.get_package_key", return_value=FAKE_KEY),
        patch("src.skill_packages.store_context", return_value=FAKE_FILE_ID),
        patch("src.skill_packages.update_context", return_value=FAKE_FILE_ID),
        patch("src.skill_packages.load_local_index", return_value={}),
        patch("src.skill_packages.save_local_index"),
        patch("src.skill_packages.log_event"),
        patch(
            "src.skill_packages._load_skill_index",
            return_value={"version": "1.0", "last_updated": "", "skills": []},
        ),
    ):
        yield


class TestSaveSkill:
    def test_new_skill_assigned_uuid(self, mock_io):
        skill = save_skill(
            name="new_skill",
            description="does something",
            instructions="step 1",
            input_schema={"type": "object", "properties": {}},
            token_id=FAKE_TOKEN,
        )
        assert skill.id  # UUID assigned
        assert skill.name == "new_skill"
        assert skill.version == "1.0.0"

    def test_new_skill_has_created_at(self, mock_io):
        skill = save_skill(
            name="new_skill",
            description="desc",
            instructions="step 1",
            input_schema={},
            token_id=FAKE_TOKEN,
        )
        assert skill.created_at  # not empty

    def test_tags_stored(self, mock_io):
        skill = save_skill(
            name="tagged_skill",
            description="desc",
            instructions="step 1",
            input_schema={},
            token_id=FAKE_TOKEN,
            tags=["alpha", "beta"],
        )
        assert skill.tags == ["alpha", "beta"]

    def test_update_preserves_created_at(self):
        existing_created_at = "2026-01-01T00:00:00Z"
        existing_entry = {
            **SKILL_ENTRY,
            "id": "skill-update-1",
            "created_at": existing_created_at,
        }
        existing_index = {"version": "1.0", "last_updated": "", "skills": [existing_entry]}

        with (
            patch("src.skill_packages.get_package_key", return_value=FAKE_KEY),
            patch("src.skill_packages.store_context", return_value=FAKE_FILE_ID),
            patch("src.skill_packages.update_context", return_value=FAKE_FILE_ID),
            patch("src.skill_packages.load_local_index", return_value={}),
            patch("src.skill_packages.save_local_index"),
            patch("src.skill_packages.log_event"),
            patch("src.skill_packages._load_skill_index", return_value=existing_index),
        ):

            skill = save_skill(
                name="analyze_contract",
                description="updated",
                instructions="new steps",
                input_schema={},
                token_id=FAKE_TOKEN,
                skill_id="skill-update-1",
            )

        assert skill.created_at == existing_created_at

    def test_uses_existing_file_id_for_update(self):
        existing_entry = {**SKILL_ENTRY, "id": "skill-upd", "file_id": "0.0.existing"}
        existing_index = {"version": "1.0", "last_updated": "", "skills": [existing_entry]}

        with (
            patch("src.skill_packages.get_package_key", return_value=FAKE_KEY) as _,
            patch("src.skill_packages.update_context", return_value="0.0.existing") as mock_update,
            patch("src.skill_packages.store_context", return_value=FAKE_FILE_ID) as mock_store,
            patch("src.skill_packages.load_local_index", return_value={}),
            patch("src.skill_packages.save_local_index"),
            patch("src.skill_packages.log_event"),
            patch("src.skill_packages._load_skill_index", return_value=existing_index),
        ):

            save_skill(
                name="analyze_contract",
                description="updated desc",
                instructions="steps",
                input_schema={},
                token_id=FAKE_TOKEN,
                skill_id="skill-upd",
            )

        # update_context should be called with the existing file_id, not store_context
        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] == "0.0.existing"


# ---------------------------------------------------------------------------
# delete_skill
# ---------------------------------------------------------------------------


class TestDeleteSkill:
    def test_deletes_existing_skill(self):
        existing_index = {"version": "1.0", "last_updated": "", "skills": [SKILL_ENTRY]}

        with (
            patch("src.skill_packages.get_package_key", return_value=FAKE_KEY),
            patch("src.skill_packages.store_context", return_value=FAKE_INDEX_FILE_ID),
            patch("src.skill_packages.update_context", return_value=FAKE_INDEX_FILE_ID),
            patch("src.skill_packages.load_local_index", return_value={}),
            patch("src.skill_packages.save_local_index"),
            patch("src.skill_packages._load_skill_index", return_value=existing_index),
        ):

            result = delete_skill("skill-001", FAKE_TOKEN)

        assert result is True

    def test_nonexistent_skill_returns_false(self):
        empty_index = {"version": "1.0", "last_updated": "", "skills": []}

        with (
            patch("src.skill_packages.get_package_key", return_value=FAKE_KEY),
            patch("src.skill_packages.store_context", return_value=FAKE_INDEX_FILE_ID),
            patch("src.skill_packages.update_context", return_value=FAKE_INDEX_FILE_ID),
            patch("src.skill_packages.load_local_index", return_value={}),
            patch("src.skill_packages.save_local_index"),
            patch("src.skill_packages._load_skill_index", return_value=empty_index),
        ):

            result = delete_skill("nonexistent-id", FAKE_TOKEN)

        assert result is False
