"""
api/services/builtin_tools.py — Built-in tools for agentic AI chat.

These tools allow the AI to interact with Pass/Drive/Mail/Calendar during conversations.
Unlike skill packages (user-defined, vault-stored), these are always available.

Tool execution flow:
1. AI requests tool use (e.g. "get_password_entries")
2. Frontend receives tool_use SSE event
3. Frontend executes tool via API call
4. Frontend sends tool_result back to AI
5. AI continues with the result

Supported tools:
- Pass: list_passwords, get_password, create_password, update_password, delete_password
- Notes: list_notes, get_note, create_note, update_note, delete_note
- Authenticator: list_totp, get_totp_code, create_totp, delete_totp
- Drive: list_files, upload_file, download_file, delete_file
- Mail: list_messages, get_message, send_message, delete_message
- Calendar: list_events, get_event, create_event, update_event, delete_event
"""

from typing import Any

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic format)
# ---------------------------------------------------------------------------

BUILTIN_TOOLS: list[dict[str, Any]] = [
    # ─── Pass / Password Manager ───────────────────────────────────────────
    {
        "name": "list_passwords",
        "description": "List all password entries in the user's encrypted password vault. Returns entry names, usernames, and URLs (passwords are not included in list view for security).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_password",
        "description": "Retrieve a specific password entry including the actual password. Use this when the user asks for a specific password.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_id": {
                    "type": "string",
                    "description": "The ID of the password entry to retrieve",
                },
            },
            "required": ["entry_id"],
        },
    },
    {
        "name": "create_password",
        "description": "Create a new password entry in the vault. Use this when the user wants to save a new password.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name/title for this password (e.g. 'Gmail', 'GitHub')",
                },
                "username": {
                    "type": "string",
                    "description": "Username or email for this account",
                },
                "password": {
                    "type": "string",
                    "description": "The password to store",
                },
                "url": {
                    "type": "string",
                    "description": "Website URL (optional)",
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes (optional)",
                },
            },
            "required": ["name", "password"],
        },
    },
    # ─── Notes / Secure Notes ──────────────────────────────────────────────
    {
        "name": "list_notes",
        "description": "List all secure notes (credit cards, documents, custom notes) in the user's vault.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_note",
        "description": "Retrieve a specific secure note with full content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "The ID of the note to retrieve",
                },
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "create_note",
        "description": "Create a new secure note (credit card, document, or custom note).",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["credit_card", "document", "custom"],
                    "description": "Type of note to create",
                },
                "title": {
                    "type": "string",
                    "description": "Title for this note",
                },
                "content": {
                    "type": "object",
                    "description": "Note content (structure depends on type)",
                },
            },
            "required": ["type", "title", "content"],
        },
    },
    # ─── Authenticator / TOTP ──────────────────────────────────────────────
    {
        "name": "list_totp",
        "description": "List all TOTP/2FA authenticator entries in the user's vault.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_totp_code",
        "description": "Generate the current TOTP code for a specific authenticator entry. The code is valid for 30 seconds.",
        "input_schema": {
            "type": "object",
            "properties": {
                "totp_id": {
                    "type": "string",
                    "description": "The ID of the TOTP entry",
                },
            },
            "required": ["totp_id"],
        },
    },
    # ─── Drive / File Storage ──────────────────────────────────────────────
    {
        "name": "list_files",
        "description": "List all files in the user's encrypted file storage.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ─── Mail / Encrypted Messaging ────────────────────────────────────────
    {
        "name": "list_messages",
        "description": "List messages in the user's encrypted mailbox (inbox or sent).",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {
                    "type": "string",
                    "enum": ["inbox", "sent"],
                    "description": "Which folder to list",
                },
            },
            "required": ["folder"],
        },
    },
    {
        "name": "send_message",
        "description": "Send an encrypted message to another user (requires their token ID).",
        "input_schema": {
            "type": "object",
            "properties": {
                "to_token_id": {
                    "type": "string",
                    "description": "Recipient's Hedera token ID (e.g. '0.0.12345')",
                },
                "subject": {
                    "type": "string",
                    "description": "Message subject",
                },
                "body": {
                    "type": "string",
                    "description": "Message body",
                },
            },
            "required": ["to_token_id", "subject", "body"],
        },
    },
    # ─── Calendar / Events ─────────────────────────────────────────────────
    {
        "name": "list_events",
        "description": "List calendar events for a specific month.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {
                    "type": "integer",
                    "description": "Year (e.g. 2026)",
                },
                "month": {
                    "type": "integer",
                    "description": "Month (1-12)",
                },
            },
            "required": ["year", "month"],
        },
    },
    {
        "name": "create_event",
        "description": "Create a new calendar event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Event title",
                },
                "date": {
                    "type": "string",
                    "description": "Event date (YYYY-MM-DD)",
                },
                "time": {
                    "type": "string",
                    "description": "Event time (HH:MM, optional)",
                },
                "description": {
                    "type": "string",
                    "description": "Event description (optional)",
                },
                "color": {
                    "type": "string",
                    "description": "Event color (optional, e.g. 'blue', 'red', 'green')",
                },
            },
            "required": ["title", "date"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool name → API endpoint mapping
# ---------------------------------------------------------------------------

TOOL_ENDPOINTS: dict[str, dict[str, str]] = {
    # Pass
    "list_passwords": {"method": "GET", "path": "/pass/entries"},
    "get_password": {"method": "GET", "path": "/pass/entry/{entry_id}"},
    "create_password": {"method": "POST", "path": "/pass/entry"},
    # Notes
    "list_notes": {"method": "GET", "path": "/pass/notes"},
    "get_note": {"method": "GET", "path": "/pass/note/{note_id}"},
    "create_note": {"method": "POST", "path": "/pass/note"},
    # TOTP
    "list_totp": {"method": "GET", "path": "/pass/totp"},
    "get_totp_code": {"method": "GET", "path": "/pass/totp/{totp_id}"},
    # Drive
    "list_files": {"method": "GET", "path": "/drive/files"},
    # Mail
    "list_messages": {"method": "GET", "path": "/mail/{folder}"},
    "send_message": {"method": "POST", "path": "/mail/send"},
    # Calendar
    "list_events": {"method": "GET", "path": "/calendar/events"},
    "create_event": {"method": "POST", "path": "/calendar/event"},
}


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return all built-in tool definitions."""
    return BUILTIN_TOOLS


def get_tool_endpoint(tool_name: str) -> dict[str, str] | None:
    """Get the API endpoint info for a tool."""
    return TOOL_ENDPOINTS.get(tool_name)
