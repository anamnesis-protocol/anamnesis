"""
api/routes/chat.py — Sovereign AI Chat endpoints.

Provides streaming chat against any configured AI model, with the user's
decrypted vault context injected as the system prompt (in action:
same sovereign context, any model, no platform lock-in).

Endpoints:
 GET /chat/models?session_id=<id> → list of available models for this user (BYOK)
 POST /chat/message → StreamingResponse (SSE) — streams AI response tokens

SSE format:
 data: {"content": "token", "done": false}
 ...
 data: {"content": "", "done": true}

Security:
 - Session must exist in session_store (validated by session_id)
 - Context is retrieved server-side from session store — client never re-sends plaintext
 - Context was decrypted from Hedera at /session/open and is zeroed at /session/close
 - The model API key never leaves the server

Patent note:
 This endpoint demonstrates model-agnostic context loading:
 the same sovereign vault context drives GPT-4o, Claude, or Gemini
 with zero modification to the context itself.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.session_store import get_session, Session
from api.services.ai_router import (
    available_models,
    stream_response,
    get_model_meta,
    recommend_model,
    MODELS,
)

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_user_keys(session: Session) -> None:
    """
    Lazily load and cache per-user AI API keys into the session.

    Called at the start of every chat request. Triggers one Supabase lookup
    the first time a real user accesses chat; cached in session for the rest
    of the session lifetime and zeroed at session close.

    Sentinel logic:
    user_id == "" → demo/testnet — skip, user_api_keys stays None
    user_api_keys is not None → already loaded, skip
    Otherwise → fetch from Supabase, set on session
    """
    if session.user_id in ("", "demo-user"):
        return  # demo/testnet — use server .env keys (user_api_keys remains None)
    if session.user_api_keys is not None:
        return  # already loaded this session
    try:
        from api.services.key_store import get_user_keys

        session.user_api_keys = get_user_keys(session.user_id)
    except Exception:
        session.user_api_keys = {}  # treat Supabase errors as "no keys configured"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str = Field(description="'user' or 'assistant'")
    content: str | list  # str for normal turns, list for tool_use/tool_result content arrays


class ChatRequest(BaseModel):
    session_id: str = Field(description="Active session UUID from /session/open")
    message: str = Field(description="The user's current message")
    model: str = Field(description="Model ID — must be in the available_models list")
    history: list[ChatMessage] = Field(
        default_factory=list,
        description=(
            "Prior conversation turns in chronological order. "
            "The server injects the system prompt automatically from the session context. "
            "Do NOT include the system prompt in history."
        ),
    )
    enable_tools: bool = Field(
        default=False,
        description=(
            "Enable built-in tools for agentic operations. "
            "When True, the AI can invoke Pass/Drive/Mail/Calendar operations during the conversation. "
            "The frontend must handle tool_use SSE events and execute tools via API calls."
        ),
    )


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

_SECTION_LABELS = {
    "soul": "SOUL DIRECTIVES",
    "user": "USER PROFILE",
    "config": "AI CONFIGURATION",
    "session_state": "SESSION CONTEXT",
    "knowledge": "KNOWLEDGE BASE",
}

_SECTION_ORDER = ["soul", "user", "config", "session_state", "knowledge"]


def build_system_prompt(
    context_sections: dict[str, str],
    model_id: str,
    token_id: str,
    query: str = "",
    vault_index=None,
) -> str:
    """
    Build the system prompt from decrypted vault context.

    Harness is always injected in full — it is the AI's identity and directives.

    Remaining sections (user, config, session_state) are loaded via RAG when a
    vault_index is available: only chunks relevant to the current query are injected.
    This keeps the prompt lean as the vault grows and prevents context overflow.

    Falls back to full-section injection when:
    - vault_index is None or empty (rank-bm25 not installed, or indexing failed)
    - RAG returns no results for the query (e.g. very short or generic message)
    """
    model_display = MODELS.get(model_id, {}).get("display", model_id)

    # Describe which vault sections are loaded so the model knows what context exists
    loaded_sections = [s for s in _SECTION_ORDER if context_sections.get(s, "").strip()]
    rag_active = vault_index is not None and vault_index.chunk_count > 0
    context_note = (
        f"Your context is loaded from a sovereign vault (token {token_id}) secured on Hedera Hashgraph. "
        f"Vault sections available: {', '.join(loaded_sections) if loaded_sections else 'none yet — vault is new'}. "
    )
    if rag_active:
        context_note += (
            f"A RAG index ({vault_index.chunk_count} chunks) is active: "
            "only the most relevant context is injected per message to keep responses focused."
        )
    else:
        context_note += "Full vault content is injected below."

    lines = [
        "You are an AI companion operating under a user-defined sovereign harness. "
        "Your identity, directives, and context are owned exclusively by your user — "
        "encrypted, stored on Hedera Hashgraph, and decrypted only with their cryptographic signature. "
        "No platform can read or alter this soul without the user's key. "
        "The human is in command. Execute their directives as configured below.",
        "",
        context_note,
        "",
    ]

    # ---- Soul: always inject in full ----
    soul = context_sections.get("soul", "").strip()
    if soul:
        lines += ["=== SOUL DIRECTIVES ===", soul, ""]

    # ---- Remaining sections: RAG-gated or full fallback ----
    non_soul = {k: v for k, v in context_sections.items() if k != "soul"}
    rag_used = False

    if vault_index is not None and vault_index.chunk_count > 0 and query.strip():
        relevant = vault_index.query(query)
        if relevant:
            rag_used = True
            lines += ["=== RETRIEVED CONTEXT ==="]
            for chunk in relevant:
                label = _SECTION_LABELS.get(chunk.section, chunk.section.upper())
                lines += [f"[{label} — {chunk.header}]", chunk.text, ""]

    if not rag_used:
        # Full injection: canonical order for known sections, then any extras
        injected: set[str] = set()
        for section_name in _SECTION_ORDER:
            if section_name == "soul":
                continue  # already injected above
            content = non_soul.get(section_name, "").strip()
            if content:
                label = _SECTION_LABELS.get(section_name, section_name.upper())
                lines += [f"=== {label} ===", content, ""]
                injected.add(section_name)
        for section_name, content in non_soul.items():
            if section_name not in injected and content.strip():
                lines += [f"=== {section_name.upper()} ===", content.strip(), ""]

    lines += [
        "---",
        f"Active model: {model_display} | Context token: {token_id} | Vault sections: {len(loaded_sections)} loaded",
        "Session cryptographically verified. Respond as the companion defined above.",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# POST /chat/keys — store API keys on an active session (no Supabase required)
# ---------------------------------------------------------------------------


class SessionKeysRequest(BaseModel):
    session_id: str
    keys: dict[str, str] = Field(
        description="provider -> api_key, e.g. {'anthropic': 'sk-ant-...'}"
    )


@router.post("/keys")
def set_session_keys(req: SessionKeysRequest):
    """
    Store AI model API keys on an active session (in-memory only).

    Keys are held on the session object and zeroed at session close.
    They are never persisted to disk or Supabase. The client never
    receives key values back — only the list of configured providers.

    Works in demo/testnet mode without any auth or Supabase dependency.
    """
    session = get_session(req.session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail=f"Session '{req.session_id}' not found or expired."
        )

    valid_providers = {meta["provider"] for meta in MODELS.values()}
    stored = []
    for provider, key in req.keys.items():
        if provider not in valid_providers:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider '{provider}'. Valid: {sorted(valid_providers)}",
            )
        if not key.strip():
            continue
        if session.user_api_keys is None:
            session.user_api_keys = {}
        session.user_api_keys[provider] = key.strip()
        stored.append(provider)

    return {"configured": stored}


# ---------------------------------------------------------------------------
# GET /chat/models
# ---------------------------------------------------------------------------


@router.get("/models")
def list_models(session_id: str | None = None):
    """
    Return AI models available for this user.

    If session_id is provided and valid, returns only models the user has
    API keys configured for (BYOK). Without session_id (or demo sessions),
    falls back to server .env keys (demo/testnet mode).
    """
    user_api_keys = None  # default: demo/testnet — use env keys
    if session_id:
        session = get_session(session_id)
        if session:
            _ensure_user_keys(session)
            user_api_keys = session.user_api_keys

    models = available_models(user_api_keys=user_api_keys)
    if not models:
        return {
            "models": [],
            "message": (
                "No AI models are active on your account. "
                "Click ⚙ to add your own API keys, or contact support."
                if (user_api_keys is not None)
                else "No AI model API keys configured on the server. Add ANTHROPIC_API_KEY to .env."
            ),
        }
    return {"models": models}


# ---------------------------------------------------------------------------
# POST /chat/recommend
# ---------------------------------------------------------------------------


class RecommendRequest(BaseModel):
    session_id: str = Field(description="Active session UUID from /session/open")
    message: str = Field(description="The user's message — used to infer task type")
    current_model: str = Field(description="Model ID currently selected in the UI")


@router.post("/recommend")
def recommend(req: RecommendRequest):
    """
    Classify the user's message and return a model recommendation.

    Core directive of every Sovereign AI Context harness:
    evaluate the task against the user's configured models and route to
    the best available option. Surface unconfigured superior models as
    sidenotes. Warn if the task requires a specific capability (e.g. vision)
    that no configured model supports.

    This is intentionally lightweight (pure Python, no AI call) so it adds
    <10 ms overhead before the main streaming response begins.

    Returns:
        task_type — "coding" | "vision" | "reasoning" | ... | "general"
        task_label — human-readable task name
        recommended_model_id — best configured model for this task
        recommended_model_display — display name
        current_model_id — what the user currently has selected
        current_is_optimal — True → no action needed, False → switch suggested
        hard_requirement — True if task requires specific model capabilities
        cannot_complete — True if hard_requirement AND no capable model configured
        sidenotes — [{model_id, display, reason}] — unconfigured better options
        profile_note — optional extra guidance (e.g. privacy note)
    """
    session = get_session(req.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{req.session_id}' not found or expired.",
        )

    _ensure_user_keys(session)

    result = recommend_model(
        message=req.message,
        current_model_id=req.current_model,
        user_api_keys=session.user_api_keys,
    )
    return result


# ---------------------------------------------------------------------------
# POST /chat/message (SSE streaming)
# ---------------------------------------------------------------------------


@router.post("/message")
async def chat_message(req: ChatRequest):
    """
    Send a message to the AI companion and stream the response via SSE.

    The server:
    1. Validates the session and retrieves the decrypted context (server-side)
    2. Builds the system prompt from the vault sections
    3. Calls the selected AI model API with streaming enabled
    4. Yields SSE tokens back to the client
    5. Records the model used on the session (for auto session_state at close)

    The client never re-sends the vault context — it stays on the server
    within the session's memory lifecycle.
    """
    # ---- Validate session ----
    session = get_session(req.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{req.session_id}' not found or expired. Open a new session.",
        )

    if not session.context_sections:
        raise HTTPException(
            status_code=409,
            detail="Session context is empty. The vault may not have been loaded correctly.",
        )

    # ---- Lazy-load user API keys (one Supabase call per session max) ----
    _ensure_user_keys(session)

    # ---- Validate model (with user's key context) ----
    try:
        get_model_meta(req.model, user_api_keys=session.user_api_keys)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not req.message.strip():
        # Allow empty message when the last history entry is a tool_result turn
        # (the agentic loop sends tool results in history with message="")
        last = req.history[-1] if req.history else None
        is_tool_result_turn = (
            last is not None
            and last.role == "user"
            and isinstance(last.content, list)
            and any(isinstance(c, dict) and c.get("type") == "tool_result" for c in last.content)
        )
        if not is_tool_result_turn:
            raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # ---- Build system prompt — RAG-gated context retrieval ----
    # vault_index was built at session open from the decrypted vault content.
    # Only chunks relevant to this specific message are injected (soul always full).
    system_prompt = build_system_prompt(
        context_sections=session.context_sections,
        model_id=req.model,
        token_id=session.token_id,
        query=req.message,
        vault_index=session.vault_index,
    )

    # ---- Track last model used (for auto session_state at close) ----
    session.last_model = req.model

    # ---- Convert history to provider format ----
    history = [{"role": msg.role, "content": msg.content} for msg in req.history]

    # ---- Stream response ----
    _user_api_keys = (
        session.user_api_keys
    )  # capture before yielding (session could close mid-stream)

    async def event_stream():
        async for chunk in stream_response(
            model_id=req.model,
            system_prompt=system_prompt,
            history=history,
            message=req.message,
            user_api_keys=_user_api_keys,
            enable_tools=req.enable_tools,
        ):
            yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering for SSE
        },
    )
