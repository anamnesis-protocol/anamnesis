"""
api/mcp_server.py — Sovereign AI Context MCP Server

A generic MCP server that exposes the user's vault as a live tool surface:

Static tools (always available):
  open_session(token_id, wallet_signature_hex)    — open vault, return session_id
  close_session(session_id, updated_sections)      — sync changes back to Hedera
  get_vault_section(session_id, section_name)      — read a specific vault section
  update_vault_section(session_id, name, content)  — write a vault section (queued for close)
  list_skills(session_id)                          — list all skill packages in vault

Dynamic tools (loaded per-session from vault):
  Each skill package stored in the user's vault is exposed as a callable MCP tool.
  Tool definitions are fetched from /skills/tools at session start.
  The AI calls a skill tool → instructions in the tool definition tell it how to execute.

Usage:
  python -m api.mcp_server --port 8001

Or via uvicorn (for multi-client use):
  uvicorn api.mcp_server:app --port 8001

Environment:
  SOVEREIGN_API_BASE  — base URL of the FastAPI backend (default: http://localhost:8000)
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import httpx

# Allow running as a module from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from mcp.server.fastmcp import FastMCP
    from mcp import types as mcp_types
except ImportError:
    raise ImportError(
        "MCP SDK not installed. Run: pip install mcp\n"
        "See: https://github.com/modelcontextprotocol/python-sdk"
    )

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_BASE = os.environ.get("SOVEREIGN_API_BASE", "http://localhost:8000")

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("sovereign-vault")

# In-process session state — maps session_id → {token_id, section_updates}
# This persists across tool calls within a single MCP client connection.
_active_session: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Helper — call the FastAPI backend
# ---------------------------------------------------------------------------


def _api(method: str, path: str, **kwargs) -> dict:
    """Synchronous HTTP call to the FastAPI backend."""
    url = f"{API_BASE}{path}"
    with httpx.Client(timeout=30.0) as client:
        resp = getattr(client, method)(url, **kwargs)
    if not resp.is_success:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise RuntimeError(f"API {method.upper()} {path} → {resp.status_code}: {detail}")
    return resp.json()


# ---------------------------------------------------------------------------
# Static tools
# ---------------------------------------------------------------------------


@mcp.tool()
def open_session(token_id: str, wallet_signature_hex: str) -> dict:
    """
    Open a vault session.

    Decrypts the user's vault from Hedera and returns the session_id.
    All subsequent tool calls use this session_id to access the vault.

    Args:
        token_id: Hedera context token ID (e.g. "0.0.12345")
        wallet_signature_hex: Wallet signature over the challenge bytes.
            Get the challenge first: POST /session/challenge with the token_id,
            then sign the returned challenge_hex with the user's wallet.

    Returns:
        session_id: Use this in all subsequent vault tool calls.
        sections: The decrypted vault sections (soul, user, config, session_state).
    """
    data = _api(
        "post",
        "/session/open",
        json={
            "token_id": token_id,
            "wallet_signature_hex": wallet_signature_hex,
        },
    )

    session_id = data["session_id"]
    _active_session["session_id"] = session_id
    _active_session["token_id"] = token_id
    _active_session["section_updates"] = {}

    # Load skills for this session
    _active_session["skills"] = _load_session_skills(session_id)

    return {
        "session_id": session_id,
        "token_id": token_id,
        "sections": data.get("vault_sections", {}),
        "skills_loaded": len(_active_session.get("skills", [])),
        "message": "Session open. Vault decrypted. Skills loaded.",
    }


@mcp.tool()
def close_session(session_id: str) -> dict:
    """
    Close the vault session and sync any updated sections back to Hedera.

    Only changed sections are pushed (diff-based sync).
    Keys are zeroed after close.

    Args:
        session_id: Active session UUID from open_session.
    """
    pending_updates = _active_session.get("section_updates", {})

    data = _api(
        "post",
        "/session/close",
        json={
            "session_id": session_id,
            "updated_sections": pending_updates,
        },
    )

    # Clear local state
    _active_session.clear()

    return {
        "sections_pushed": data.get("sections_pushed", []),
        "message": "Session closed. Vault synced to Hedera.",
    }


@mcp.tool()
def get_vault_section(session_id: str, section_name: str) -> dict:
    """
    Read a specific vault section.

    Available sections: soul, user, config, session_state.
    Custom sections (if any) are also accessible.

    Args:
        session_id: Active session UUID.
        section_name: Name of the section to read.
    """
    data = _api("get", f"/vault/section/{section_name}", params={"session_id": session_id})
    return {
        "section_name": section_name,
        "content": data.get("content", ""),
    }


@mcp.tool()
def update_vault_section(session_id: str, section_name: str, content: str) -> dict:
    """
    Write updated content to a vault section.

    The update is queued locally and pushed to Hedera when close_session is called.
    Only changed sections are pushed (diff-based sync keeps HFS writes minimal).

    Args:
        session_id: Active session UUID.
        section_name: Section to update (soul, user, config, session_state).
        content: New content for the section.
    """
    if _active_session.get("session_id") != session_id:
        raise ValueError(f"No active session matching '{session_id}'.")

    _active_session.setdefault("section_updates", {})[section_name] = content
    return {
        "section_name": section_name,
        "queued": True,
        "message": f"Section '{section_name}' queued for sync on session close.",
    }


@mcp.tool()
def list_skills(session_id: str) -> dict:
    """
    List all skill packages available in this vault.

    Skills are MCP tool definitions stored encrypted in the vault.
    They represent learned tasks that the AI can pick up without re-teaching.

    Args:
        session_id: Active session UUID.
    """
    data = _api("get", "/skills", params={"session_id": session_id})
    return {
        "token_id": data.get("token_id"),
        "skills": data.get("skills", []),
        "count": len(data.get("skills", [])),
    }


@mcp.tool()
def save_skill_to_vault(
    session_id: str,
    name: str,
    description: str,
    instructions: str,
    input_schema: str,
    tags: str = "",
    skill_id: str = "",
) -> dict:
    """
    Package a learned task as a skill and store it in the vault.

    Once saved, this skill will be available as a tool in future sessions
    without needing to re-teach the AI. This implements the P1 patent
    'skill packages' claim — portable, encrypted, vault-stored knowledge.

    Args:
        session_id: Active session UUID.
        name: Skill name (snake_case, e.g. 'analyze_solidity_contract').
        description: What this skill does (shown to AI as tool description).
        instructions: Detailed step-by-step instructions for performing the task.
        input_schema: JSON string of the JSON Schema for inputs. Example:
            '{"type":"object","properties":{"contract":{"type":"string"}},"required":["contract"]}'
        tags: Comma-separated tags for filtering (e.g. "security,blockchain").
        skill_id: Provide to update an existing skill; omit to create new.
    """
    try:
        schema = json.loads(input_schema)
    except json.JSONDecodeError:
        schema = {"type": "object", "properties": {}}

    tag_list = [t.strip() for t in tags.split(",")] if tags.strip() else []

    payload: dict = {
        "name": name,
        "description": description,
        "instructions": instructions,
        "input_schema": schema,
        "tags": tag_list,
    }
    if skill_id:
        payload["skill_id"] = skill_id

    data = _api("post", "/skills", params={"session_id": session_id}, json=payload)
    return data


# ---------------------------------------------------------------------------
# Dynamic skill tool loader
# ---------------------------------------------------------------------------


def _load_session_skills(session_id: str) -> list[dict]:
    """
    Load all skill tools from the vault for this session.
    Returns a list of MCP tool definitions.
    """
    try:
        data = _api("get", "/skills/tools", params={"session_id": session_id})
        return data.get("tools", [])
    except Exception:
        return []


def _register_dynamic_skill(tool_def: dict) -> None:
    """
    Register a skill from the vault as a live MCP tool.

    The tool's handler reads the _instructions field from the tool definition
    and returns them to the AI along with the input arguments.
    """
    name = tool_def.get("name", "unknown_skill")
    description = tool_def.get("description", "")
    instructions = tool_def.get("_instructions", "")
    input_schema = tool_def.get("inputSchema", {"type": "object", "properties": {}})

    # Build the function dynamically — captures name, description, instructions
    def _skill_handler(**kwargs: Any) -> dict:
        return {
            "skill": name,
            "instructions": instructions,
            "inputs": kwargs,
            "message": (
                f"Execute skill '{name}' with the provided inputs by following the instructions above. "
                "Return the result when complete."
            ),
        }

    _skill_handler.__name__ = name
    _skill_handler.__doc__ = description

    # Register with FastMCP
    mcp.tool(name=name)(_skill_handler)


def register_session_skills(session_id: str) -> int:
    """
    Load and register all vault skills as MCP tools for this session.
    Called after open_session. Returns number of skills registered.
    """
    tools = _load_session_skills(session_id)
    for tool_def in tools:
        try:
            _register_dynamic_skill(tool_def)
        except Exception:
            pass
    return len(tools)


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


@mcp.resource("vault://session/{session_id}/sections")
def get_session_sections(session_id: str) -> str:
    """All vault sections for this session as JSON."""
    try:
        data = _api("get", "/vault/sections", params={"session_id": session_id})
        return json.dumps(data, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.resource("vault://session/{session_id}/skills")
def get_session_skills_resource(session_id: str) -> str:
    """All skill tools for this session as JSON."""
    try:
        data = _api("get", "/skills/tools", params={"session_id": session_id})
        return json.dumps(data, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sovereign AI Context MCP Server")
    parser.add_argument("--port", type=int, default=8001, help="Port to listen on")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse"],
        help="Transport: stdio (Claude Desktop) or sse (web)",
    )
    args = parser.parse_args()

    print(f"Starting Sovereign AI Context MCP server (transport={args.transport})")
    print(f"Backend API: {API_BASE}")
    mcp.run(transport=args.transport)
