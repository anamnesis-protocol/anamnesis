"""
skill_packages.py — Skill Package Layer

Implements P1 patent "skill packages" claim:
When an AI learns to perform a task → package the knowledge as an MCP tool
definition → encrypt and store in vault → load dynamically at session open
→ AI picks up the skill without re-teaching.

Skill schema (encrypted JSON on HFS):
{
    "id": "uuid4",
    "name": "analyze_solidity_contract",
    "description": "Analyzes a Solidity smart contract for security vulnerabilities",
    "version": "1.0.0",
    "created_at": "2026-04-02T00:00:00Z",
    "updated_at": "2026-04-02T00:00:00Z",
    "tags": ["security", "solidity", "blockchain"],
    "input_schema": {
        "type": "object",
        "properties": {
            "contract_code": {"type": "string", "description": "Solidity source code"},
            "focus": {"type": "string", "enum": ["reentrancy", "overflow", "all"]}
        },
        "required": ["contract_code"]
    },
    "instructions": "Step-by-step instructions for the AI to perform this task...",
    "examples": [
        {"input": {"contract_code": "..."}, "output": "..."}
    ]
}

Skill index (encrypted JSON on HFS):
{
    "version": "1.0",
    "last_updated": "2026-04-02",
    "skills": [
        {
            "id": "uuid4",
            "name": "skill_name",
            "description": "...",
            "tags": ["tag1"],
            "file_id": "0.0.12345",
            "version": "1.0.0",
            "created_at": "..."
        }
    ]
}

Usage:
    from src.skill_packages import push_skill, pull_skill, query_skills, push_skill_index
"""

import json
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional

from src.context_storage import store_context, load_context, update_context
from src.crypto import compress, decompress
from src.vault import (
    get_package_key,
    _make_package_aad,
    _make_package_index_aad,
    load_local_index,
    save_local_index,
)
from src.event_log import log_event

# ---------------------------------------------------------------------------
# Skill metadata model
# ---------------------------------------------------------------------------


@dataclass
class SkillMetadata:
    id: str
    name: str
    description: str
    tags: list[str]
    file_id: str
    version: str
    created_at: str


@dataclass
class SkillPackage:
    id: str
    name: str
    description: str
    version: str
    created_at: str
    updated_at: str
    tags: list[str]
    input_schema: dict
    instructions: str
    examples: list[dict] = field(default_factory=list)

    def to_mcp_tool(self) -> dict:
        """Convert to MCP tool definition format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "_skill_id": self.id,
            "_instructions": self.instructions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillPackage":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            version=data.get("version", "1.0.0"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            tags=data.get("tags", []),
            input_schema=data.get("input_schema", {"type": "object", "properties": {}}),
            instructions=data.get("instructions", ""),
            examples=data.get("examples", []),
        )


# ---------------------------------------------------------------------------
# Skill index helpers
# ---------------------------------------------------------------------------

_SKILL_INDEX_KEY = "skill_index"


def _load_skill_index(token_id: str) -> dict:
    """Load the local skill index cache, or return empty index."""
    local_index = load_local_index()
    skill_index_file_id = local_index.get(_SKILL_INDEX_KEY)
    if not skill_index_file_id:
        return {"version": "1.0", "last_updated": "", "skills": []}

    skill_key = get_package_key(token_id)
    aad = _make_package_index_aad(token_id)
    try:
        raw = load_context(skill_index_file_id, skill_key, aad)
        return json.loads(decompress(raw).decode("utf-8"))
    except Exception:
        return {"version": "1.0", "last_updated": "", "skills": []}


# ---------------------------------------------------------------------------
# Push a skill to HFS
# ---------------------------------------------------------------------------


def push_skill(
    skill: SkillPackage,
    token_id: str,
    existing_file_id: Optional[str] = None,
) -> str:
    """
    Encrypt and push a skill package to HFS.

    Returns the HFS file_id where the skill is stored.
    """
    skill_key = get_package_key(token_id)
    aad = _make_package_aad(skill.name, token_id)

    payload = json.dumps(asdict(skill), ensure_ascii=False).encode("utf-8")
    compressed = compress(payload)

    if existing_file_id:
        file_id = update_context(existing_file_id, skill_key, compressed, aad)
    else:
        file_id = store_context(skill_key, compressed, aad)

    try:
        log_event(
            event_type="SKILL_PUSHED",
            payload={"skill_id": skill.id, "skill_name": skill.name, "token_id": token_id},
        )
    except Exception:
        pass

    return file_id


# ---------------------------------------------------------------------------
# Pull a skill from HFS
# ---------------------------------------------------------------------------


def pull_skill(file_id: str, token_id: str, skill_name: str) -> SkillPackage:
    """
    Load and decrypt a skill package from HFS.
    """
    skill_key = get_package_key(token_id)
    aad = _make_package_aad(skill_name, token_id)

    raw = load_context(file_id, skill_key, aad)
    data = json.loads(decompress(raw).decode("utf-8"))
    return SkillPackage.from_dict(data)


# ---------------------------------------------------------------------------
# Query skill index by tags or name
# ---------------------------------------------------------------------------


def query_skills(
    token_id: str,
    tags: Optional[list[str]] = None,
    name_contains: Optional[str] = None,
    limit: int = 20,
) -> list[SkillMetadata]:
    """
    Query the skill index. Returns matching SkillMetadata entries.

    If no filters: returns all skills up to limit.
    tags: skill must have at least one matching tag.
    name_contains: case-insensitive substring match on skill name.
    """
    index = _load_skill_index(token_id)
    results = []

    for entry in index.get("skills", []):
        if tags:
            if not any(t.lower() in [et.lower() for et in entry.get("tags", [])] for t in tags):
                continue
        if name_contains:
            if name_contains.lower() not in entry.get("name", "").lower():
                continue
        results.append(
            SkillMetadata(
                id=entry["id"],
                name=entry["name"],
                description=entry.get("description", ""),
                tags=entry.get("tags", []),
                file_id=entry["file_id"],
                version=entry.get("version", "1.0.0"),
                created_at=entry.get("created_at", ""),
            )
        )
        if len(results) >= limit:
            break

    return results


# ---------------------------------------------------------------------------
# Push skill index to HFS
# ---------------------------------------------------------------------------


def push_skill_index(skills: list[SkillMetadata], token_id: str) -> str:
    """
    Build and push the skill index to HFS.
    Returns the index file_id.
    """
    skill_key = get_package_key(token_id)
    aad = _make_package_index_aad(token_id)

    index = {
        "version": "1.0",
        "last_updated": datetime.now(timezone.utc).date().isoformat(),
        "skills": [asdict(s) for s in skills],
    }
    payload = json.dumps(index, ensure_ascii=False).encode("utf-8")
    compressed = compress(payload)

    local_index = load_local_index()
    existing_file_id = local_index.get(_SKILL_INDEX_KEY)

    if existing_file_id:
        file_id = update_context(existing_file_id, skill_key, compressed, aad)
    else:
        file_id = store_context(skill_key, compressed, aad)

    local_index[_SKILL_INDEX_KEY] = file_id
    save_local_index(local_index)

    return file_id


# ---------------------------------------------------------------------------
# Save or update a skill (push + update index)
# ---------------------------------------------------------------------------


def save_skill(
    name: str,
    description: str,
    instructions: str,
    input_schema: dict,
    token_id: str,
    tags: Optional[list[str]] = None,
    examples: Optional[list[dict]] = None,
    skill_id: Optional[str] = None,
    version: str = "1.0.0",
) -> SkillPackage:
    """
    Create or update a skill. Pushes to HFS and updates the index.

    If skill_id is provided, updates the existing skill.
    Otherwise creates a new skill.

    Returns the saved SkillPackage.
    """
    now = datetime.now(timezone.utc).isoformat()
    is_new = skill_id is None
    skill_id = skill_id or str(uuid.uuid4())

    skill = SkillPackage(
        id=skill_id,
        name=name,
        description=description,
        version=version,
        created_at=now if is_new else "",
        updated_at=now,
        tags=tags or [],
        input_schema=input_schema,
        instructions=instructions,
        examples=examples or [],
    )

    # Check if skill already has a file_id (for update)
    index = _load_skill_index(token_id)
    existing = next((s for s in index.get("skills", []) if s.get("id") == skill_id), None)
    existing_file_id = existing.get("file_id") if existing else None

    # If updating, preserve original created_at
    if existing and not is_new:
        skill.created_at = existing.get("created_at", now)

    file_id = push_skill(skill, token_id, existing_file_id=existing_file_id)

    # Update index
    skill_entries = [s for s in index.get("skills", []) if s.get("id") != skill_id]
    skill_entries.append(
        asdict(
            SkillMetadata(
                id=skill.id,
                name=skill.name,
                description=skill.description,
                tags=skill.tags,
                file_id=file_id,
                version=skill.version,
                created_at=skill.created_at,
            )
        )
    )

    skills_meta = [SkillMetadata(**s) for s in skill_entries]
    push_skill_index(skills_meta, token_id)

    return skill


# ---------------------------------------------------------------------------
# Delete a skill from the index (does not remove HFS file — HFS is immutable)
# ---------------------------------------------------------------------------


def delete_skill(skill_id: str, token_id: str) -> bool:
    """
    Remove a skill from the index. Returns True if found and removed.
    Note: HFS files are immutable — the file remains on HFS but is no longer referenced.
    """
    index = _load_skill_index(token_id)
    before = len(index.get("skills", []))
    remaining = [s for s in index.get("skills", []) if s.get("id") != skill_id]

    if len(remaining) == before:
        return False

    skills_meta = [SkillMetadata(**s) for s in remaining]
    push_skill_index(skills_meta, token_id)
    return True
