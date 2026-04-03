"""
api/routes/skills.py — Skill package CRUD endpoints.

Skill packages are encrypted MCP tool definitions stored in the user's vault.
When Drake learns a task, it packages the knowledge as a skill → stored encrypted
on HFS → loaded dynamically at session open → any AI model picks it up without re-teaching.

Endpoints:
  GET  /skills?session_id=<id>             → list all skills in this vault
  GET  /skills/{skill_id}?session_id=<id>  → get a specific skill (full definition)
  POST /skills?session_id=<id>             → create or update a skill
  DELETE /skills/{skill_id}?session_id=<id> → remove skill from index
  GET  /skills/tools?session_id=<id>       → list skills as MCP tool definitions
"""

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.session_store import get_session
from src.skill_packages import (
    SkillPackage,
    SkillMetadata,
    save_skill,
    pull_skill,
    query_skills,
    delete_skill,
)

router = APIRouter(prefix="/skills", tags=["skills"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SkillSaveRequest(BaseModel):
    name: str = Field(description="Unique skill name (snake_case recommended)")
    description: str = Field(description="What this skill does")
    instructions: str = Field(description="Step-by-step instructions for the AI to perform this task")
    input_schema: dict = Field(
        default_factory=lambda: {"type": "object", "properties": {}},
        description="JSON Schema for the skill's input parameters",
    )
    tags: list[str] = Field(default_factory=list, description="Tags for filtering")
    examples: list[dict] = Field(default_factory=list, description="Example inputs and outputs")
    skill_id: Optional[str] = Field(default=None, description="Provide to update an existing skill")
    version: str = Field(default="1.0.0")


class SkillSummary(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str]
    version: str
    created_at: str


class SkillDetail(SkillSummary):
    updated_at: str
    input_schema: dict
    instructions: str
    examples: list[dict]


class SkillListResponse(BaseModel):
    token_id: str
    skills: list[SkillSummary]


class SkillSaveResponse(BaseModel):
    skill_id: str
    name: str
    version: str
    message: str


class SkillDeleteResponse(BaseModel):
    skill_id: str
    deleted: bool
    message: str


class McpToolsResponse(BaseModel):
    token_id: str
    tools: list[dict]


# ---------------------------------------------------------------------------
# GET /skills — list all skills
# ---------------------------------------------------------------------------

@router.get("", response_model=SkillListResponse)
def list_skills(
    session_id: str = Query(description="Active session UUID from /session/open"),
    tags: Optional[str] = Query(default=None, description="Comma-separated tag filter"),
    name_contains: Optional[str] = Query(default=None),
) -> SkillListResponse:
    """
    List all skills in this vault. Optionally filter by tags or name.
    Requires an active session — skill keys are derived from the session.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    skills = query_skills(
        token_id=session.token_id,
        tags=tag_list,
        name_contains=name_contains,
    )

    return SkillListResponse(
        token_id=session.token_id,
        skills=[
            SkillSummary(
                id=s.id,
                name=s.name,
                description=s.description,
                tags=s.tags,
                version=s.version,
                created_at=s.created_at,
            )
            for s in skills
        ],
    )


# ---------------------------------------------------------------------------
# GET /skills/tools — list skills as MCP tool definitions
# ---------------------------------------------------------------------------

@router.get("/tools", response_model=McpToolsResponse)
def list_skill_tools(
    session_id: str = Query(description="Active session UUID from /session/open"),
) -> McpToolsResponse:
    """
    Return all skills as MCP tool definitions.

    This is what the MCP server calls at session start to load skills dynamically.
    Each tool includes name, description, inputSchema, and the _instructions field
    that tells the AI how to execute the skill.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    skills_meta = query_skills(token_id=session.token_id)
    tools = []

    for meta in skills_meta:
        try:
            skill = pull_skill(meta.file_id, session.token_id, meta.name)
            tools.append(skill.to_mcp_tool())
        except Exception:
            # If a skill fails to load, skip it rather than failing the whole list
            pass

    return McpToolsResponse(token_id=session.token_id, tools=tools)


# ---------------------------------------------------------------------------
# GET /skills/{skill_id} — get a specific skill
# ---------------------------------------------------------------------------

@router.get("/{skill_id}", response_model=SkillDetail)
def get_skill(
    skill_id: str,
    session_id: str = Query(description="Active session UUID from /session/open"),
) -> SkillDetail:
    """Load the full definition of a specific skill."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    skills_meta = query_skills(token_id=session.token_id)
    meta = next((s for s in skills_meta if s.id == skill_id), None)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found in vault.")

    try:
        skill = pull_skill(meta.file_id, session.token_id, meta.name)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to load skill from HFS: {exc}")

    return SkillDetail(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        tags=skill.tags,
        version=skill.version,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
        input_schema=skill.input_schema,
        instructions=skill.instructions,
        examples=skill.examples,
    )


# ---------------------------------------------------------------------------
# POST /skills — create or update a skill
# ---------------------------------------------------------------------------

@router.post("", response_model=SkillSaveResponse)
def upsert_skill(
    req: SkillSaveRequest,
    session_id: str = Query(description="Active session UUID from /session/open"),
) -> SkillSaveResponse:
    """
    Create a new skill or update an existing one.

    If skill_id is provided: updates the existing skill.
    Otherwise: creates a new skill with a generated UUID.

    The skill is encrypted and pushed to HFS. The skill index is updated.
    On next session open, the new skill will be available as an MCP tool.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    try:
        skill = save_skill(
            name=req.name,
            description=req.description,
            instructions=req.instructions,
            input_schema=req.input_schema,
            token_id=session.token_id,
            tags=req.tags,
            examples=req.examples,
            skill_id=req.skill_id,
            version=req.version,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to save skill: {exc}")

    action = "updated" if req.skill_id else "created"
    return SkillSaveResponse(
        skill_id=skill.id,
        name=skill.name,
        version=skill.version,
        message=f"Skill '{skill.name}' {action} and stored in vault.",
    )


# ---------------------------------------------------------------------------
# DELETE /skills/{skill_id} — remove skill from index
# ---------------------------------------------------------------------------

@router.delete("/{skill_id}", response_model=SkillDeleteResponse)
def remove_skill(
    skill_id: str,
    session_id: str = Query(description="Active session UUID from /session/open"),
) -> SkillDeleteResponse:
    """
    Remove a skill from the vault index.

    Note: HFS files are immutable — the file remains on Hedera but is no
    longer referenced by the index and will not be loaded at session open.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    try:
        deleted = delete_skill(skill_id, session.token_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to update skill index: {exc}")

    return SkillDeleteResponse(
        skill_id=skill_id,
        deleted=deleted,
        message="Skill removed from index." if deleted else "Skill not found.",
    )
