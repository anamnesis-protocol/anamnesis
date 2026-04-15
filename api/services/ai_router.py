"""
api/services/ai_router.py — Unified AI model abstraction layer.

Routes chat messages to OpenAI, Anthropic, or Google based on model selection.
Each provider returns an async generator yielding SSE-formatted strings.

Only models whose API key is configured are advertised via available_models().
This implements the patent's model-agnostic claim: same encrypted vault context,
any AI model — the user owns the brain, not the platform.

Key resolution (BYOK model):
 user_api_keys = None → demo/testnet: fall back to server .env keys
 user_api_keys = {} → real user with no keys configured: no models shown
 user_api_keys = {...} → real user: use their keys only, no .env fallback

Environment variables (used only in demo/testnet mode):
 OPENAI_API_KEY — enables OpenAI models (gpt-4o, gpt-4-turbo)
 ANTHROPIC_API_KEY — enables Anthropic models (claude-3-5-sonnet, claude-3-opus)
 GOOGLE_API_KEY — enables Google models (gemini-1.5-pro, gemini-1.5-flash)
 MISTRAL_API_KEY — enables Mistral models (mistral-large, mistral-small)
 GROQ_API_KEY — enables Groq-hosted models (llama-3.3-70b, mixtral-8x7b)
 OLLAMA_BASE_URL — enables Ollama local models (default: http://localhost:11434)
 For Ollama, the user stores their server URL as the "key".
"""

import json
import os
from typing import AsyncIterator, Any

from api.services.builtin_tools import get_tool_definitions

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODELS: dict[str, dict] = {
    # ── Anthropic / Claude (default) ───
    # Claude is the platform default — included in every subscription.
    # Listed first so it is the pre-selected model in the UI.
    "claude-sonnet-4-5": {
        "provider": "anthropic",
        "display": "Claude Sonnet 4.5 ★",  # ★ = platform default
        "env_key": "ANTHROPIC_API_KEY",
    },
    "claude-opus-4-6": {
        "provider": "anthropic",
        "display": "Claude Opus 4.6",
        "env_key": "ANTHROPIC_API_KEY",
    },
    # ── OpenAI ────────────────────────────────────────────────────────────────
    "gpt-4o": {
        "provider": "openai",
        "display": "GPT-4o (OpenAI)",
        "env_key": "OPENAI_API_KEY",
    },
    "gpt-4-turbo": {
        "provider": "openai",
        "display": "GPT-4 Turbo (OpenAI)",
        "env_key": "OPENAI_API_KEY",
    },
    # ── Google Gemini ─────────────────────────────────────────────────────────
    "gemini-1.5-pro": {
        "provider": "google",
        "display": "Gemini 1.5 Pro (Google)",
        "env_key": "GOOGLE_API_KEY",
    },
    "gemini-1.5-flash": {
        "provider": "google",
        "display": "Gemini 1.5 Flash (Google)",
        "env_key": "GOOGLE_API_KEY",
    },
    # ── Mistral (EU-based, privacy-first) ────────────────────────────────────
    "mistral-large-latest": {
        "provider": "mistral",
        "display": "Mistral Large (EU Privacy)",
        "env_key": "MISTRAL_API_KEY",
    },
    "mistral-small-latest": {
        "provider": "mistral",
        "display": "Mistral Small (EU Privacy)",
        "env_key": "MISTRAL_API_KEY",
    },
    # ── Groq (fast inference, OpenAI-compatible) ──────────────────────────────
    "llama-3.3-70b-versatile": {
        "provider": "groq",
        "display": "Llama 3.3 70B — Fast (Groq)",
        "env_key": "GROQ_API_KEY",
    },
    "mixtral-8x7b-32768": {
        "provider": "groq",
        "display": "Mixtral 8x7B — Fast (Groq)",
        "env_key": "GROQ_API_KEY",
    },
    # ── OpenRouter (unified gateway — 100+ models, one API key) ─────────────
    # Model IDs use "openrouter/" prefix; prefix is stripped before the API call.
    # Full model list: https://openrouter.ai/models
    "openrouter/anthropic/claude-sonnet-4-5": {
        "provider": "openrouter",
        "display": "Claude Sonnet 4.5 via OpenRouter",
        "env_key": "OPENROUTER_PAID_KEY",  # requires credits — BYOK or paid operator key
    },
    "openrouter/google/gemini-2.0-flash-001": {
        "provider": "openrouter",
        "display": "Gemini 2.0 Flash via OpenRouter",
        "env_key": "OPENROUTER_PAID_KEY",  # requires credits — BYOK or paid operator key
    },
    "openrouter/openai/gpt-oss-20b:free": {
        "provider": "openrouter",
        "display": "GPT OSS 20B (Free)",
        "env_key": "OPENROUTER_API_KEY",
    },
    "openrouter/openai/gpt-oss-120b:free": {
        "provider": "openrouter",
        "display": "GPT OSS 120B (Free)",
        "env_key": "OPENROUTER_API_KEY",
    },
    "openrouter/meta-llama/llama-3.3-70b-instruct:free": {
        "provider": "openrouter",
        "display": "Llama 3.3 70B (Free)",
        "env_key": "OPENROUTER_API_KEY",
    },
    "openrouter/google/gemma-3-12b-it:free": {
        "provider": "openrouter",
        "display": "Gemma 3 12B (Free)",
        "env_key": "OPENROUTER_API_KEY",
    },
    "openrouter/nvidia/nemotron-3-super-120b-a12b:free": {
        "provider": "openrouter",
        "display": "Nemotron 120B (Free)",
        "env_key": "OPENROUTER_API_KEY",
    },
    # ── xAI / Grok ───────────────────────────────────────────────────────────
    "grok-3": {
        "provider": "xai",
        "display": "Grok 3 (xAI)",
        "env_key": "XAI_API_KEY",
    },
    "grok-3-mini": {
        "provider": "xai",
        "display": "Grok 3 Mini (xAI)",
        "env_key": "XAI_API_KEY",
    },
    # ── Ollama (local models — zero data leaves the machine) ─────────────────
    # env_key holds the server base URL, not an API key.
    # User must have pulled the model: `ollama pull llama3.2`
    "ollama/llama3.2": {
        "provider": "ollama",
        "display": "Llama 3.2 — Local (Ollama)",
        "env_key": "OLLAMA_BASE_URL",
    },
    "ollama/mistral": {
        "provider": "ollama",
        "display": "Mistral 7B — Local (Ollama)",
        "env_key": "OLLAMA_BASE_URL",
    },
    "ollama/phi3": {
        "provider": "ollama",
        "display": "Phi-3 Mini — Local (Ollama)",
        "env_key": "OLLAMA_BASE_URL",
    },
}


# ---------------------------------------------------------------------------
# Task profiles — drives model recommendation logic
# ---------------------------------------------------------------------------
# Each profile defines:
# keywords — lowercase substrings checked against the user's message
# preferred_models — ordered list of model IDs, best fit first
# hard_requirement — True if the task CANNOT be done without these models
# hard_requirement_reason — shown to user when no capable model is configured
# profile_note — optional extra context surfaced in the recommendation
#
# This is the core routing intelligence of every Sovereign AI Context harness.
# It evaluates the user's intent and maps it to the best available model so the
# harness always steers the user toward the right tool for the job.
# ---------------------------------------------------------------------------

_TASK_PROFILES: dict[str, dict] = {
    # ── Vision / multimodal ────────────────────────────────────────────────
    "vision": {
        "label": "Image / visual analysis",
        "keywords": [
            "image",
            "screenshot",
            "photo",
            "picture",
            "diagram",
            "chart",
            "visual",
            "what do you see",
            "look at this",
            "analyze this image",
            "describe the image",
            "what's in this",
            "what is in the",
        ],
        "preferred_models": [
            "gpt-4o",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "claude-3-5-sonnet-20241022",
        ],
        "hard_requirement": True,
        "hard_requirement_reason": (
            "Image analysis requires a multimodal model. "
            "This task cannot be completed with a text-only model."
        ),
    },
    # ── Code generation & debugging ────────────────────────────────────────
    "coding": {
        "label": "Code generation / debugging",
        "keywords": [
            "code",
            "function",
            "debug",
            "error",
            "traceback",
            "exception",
            "class",
            "implement",
            "refactor",
            "script",
            "algorithm",
            "api endpoint",
            "sql",
            "python",
            "javascript",
            "typescript",
            "java",
            "golang",
            "rust",
            "bash",
            "dockerfile",
            "kubernetes",
            "unit test",
            "pytest",
            "jest",
            "regex",
            "compile",
            "runtime",
            "syntax",
            "doesn't work",
            "why isn't",
            "fix this",
            "bug",
        ],
        "preferred_models": [
            "gpt-4o",
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "llama-3.3-70b-versatile",
            "mistral-large-latest",
        ],
        "hard_requirement": False,
    },
    # ── Deep reasoning / planning ──────────────────────────────────────────
    "reasoning": {
        "label": "Analysis / planning / strategy",
        "keywords": [
            "analyze",
            "analysis",
            "plan",
            "strategy",
            "compare",
            "evaluate",
            "architecture",
            "system design",
            "decision",
            "trade-off",
            "pros and cons",
            "think through",
            "break down",
            "step by step",
            "complex problem",
            "recommend an approach",
            "best way to",
            "should i",
            "which option",
        ],
        "preferred_models": [
            "claude-3-opus-20240229",
            "gpt-4o",
            "claude-3-5-sonnet-20241022",
            "gemini-1.5-pro",
            "mistral-large-latest",
        ],
        "hard_requirement": False,
    },
    # ── Creative writing ───────────────────────────────────────────────────
    "creative": {
        "label": "Creative writing",
        "keywords": [
            "write a",
            "draft",
            "story",
            "poem",
            "poem",
            "essay",
            "blog post",
            "email",
            "cover letter",
            "pitch",
            "marketing copy",
            "headline",
            "rewrite",
            "make this sound",
            "persuasive",
            "narrative",
            "creative",
            "engaging",
            "tone",
        ],
        "preferred_models": [
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "gpt-4o",
            "mistral-large-latest",
        ],
        "hard_requirement": False,
    },
    # ── Long document / context ────────────────────────────────────────────
    "long_context": {
        "label": "Long document processing",
        "keywords": [
            "entire document",
            "full file",
            "all of this",
            "long context",
            "comprehensive analysis",
            "summarize this document",
            "read through all",
            "entire codebase",
            "whole file",
            "everything in this",
            "multiple files",
        ],
        "preferred_models": [
            "gemini-1.5-pro",
            "gpt-4o",
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
        ],
        "hard_requirement": False,
    },
    # ── Fast / simple queries ──────────────────────────────────────────────
    "fast": {
        "label": "Quick / simple query",
        "keywords": [
            "quick question",
            "briefly",
            "tldr",
            "tl;dr",
            "short answer",
            "in one sentence",
            "what is the definition",
            "remind me",
            "how do i install",
            "what's the syntax",
            "quick summary",
        ],
        "preferred_models": [
            "gemini-1.5-flash",
            "gpt-4o",
            "llama-3.3-70b-versatile",
            "mistral-small-latest",
            "mixtral-8x7b-32768",
        ],
        "hard_requirement": False,
    },
    # ── Confidential / private data ────────────────────────────────────────
    "privacy": {
        "label": "Confidential / private data",
        "keywords": [
            "confidential",
            "sensitive data",
            "personal data",
            "pii",
            "local only",
            "no cloud",
            "don't share this",
            "off the record",
            "proprietary",
            "internal only",
            "private information",
            "hipaa",
            "gdpr",
            "ferpa",
        ],
        "preferred_models": [
            "ollama/llama3.2",
            "ollama/mistral",
            "ollama/phi3",
            "mistral-large-latest",
            "mistral-small-latest",
        ],
        "hard_requirement": False,
        "profile_note": (
            "For maximum privacy, local Ollama models keep all data on your machine — "
            "zero data leaves your network."
        ),
    },
}


def _resolve_api_key(env_key: str, provider: str, user_api_keys: dict | None) -> str | None:
    """
    Resolve the API key for a provider.

    - user_api_keys is None → demo/testnet: return server .env value
    - user_api_keys is dict → real user: return their key (no .env fallback)
    """
    if user_api_keys is None:
        return os.getenv(env_key)
    return user_api_keys.get(provider)


def available_models(user_api_keys: dict | None = None) -> list[dict]:
    """
    Return only models whose provider API key is configured.
    Preserves registry order (OpenAI first, then Anthropic, then Google).

    Args:
        user_api_keys: None = demo/testnet (env fallback), dict = user's own keys.
    """
    result = []
    for model_id, meta in MODELS.items():
        key = _resolve_api_key(meta["env_key"], meta["provider"], user_api_keys)
        if key:
            result.append(
                {
                    "id": model_id,
                    "display": meta["display"],
                    "provider": meta["provider"],
                    "available": True,
                }
            )
    return result


def get_model_meta(model_id: str, user_api_keys: dict | None = None) -> dict:
    """
    Return model metadata. Raises ValueError if model unknown or not configured.

    Args:
        user_api_keys: None = demo/testnet (env fallback), dict = user's own keys.
    """
    meta = MODELS.get(model_id)
    if not meta:
        raise ValueError(f"Unknown model: {model_id}")
    key = _resolve_api_key(meta["env_key"], meta["provider"], user_api_keys)
    if not key:
        raise ValueError(f"Model '{model_id}' is not configured")
    return meta


# ---------------------------------------------------------------------------
# Model recommendation
# ---------------------------------------------------------------------------


def recommend_model(
    message: str,
    current_model_id: str,
    user_api_keys: dict | None,
) -> dict:
    """
    Classify the user's message and recommend the best configured model.

    Core directive of sovereign AI context: before each response,
    evaluate the task against the user's configured models and route to the
    best tool available — or tell them what they're missing.

    Returns:
        task_type — matched profile key ("coding", "vision", …) or "general"
        task_label — human-readable description
        recommended_model_id — best configured model ID for this task
        recommended_model_display — display name of recommended model
        current_model_id — the model the user currently has selected
        current_is_optimal — True if current selection is already the best configured option
        hard_requirement — True if the task needs specific model capabilities
        cannot_complete — True if hard_requirement AND no capable model is configured
        sidenotes — up to 2 unconfigured models that would do this better
        profile_note — optional extra context (e.g. privacy guidance)
    """
    msg_lower = message.lower()
    configured_ids = {m["id"] for m in available_models(user_api_keys)}

    # ── Classify task (first keyword match wins) ──────────────────────────
    matched_name: str | None = None
    matched_profile: dict | None = None
    for profile_name, profile in _TASK_PROFILES.items():
        if any(kw in msg_lower for kw in profile["keywords"]):
            matched_name = profile_name
            matched_profile = profile
            break

    # No specific task detected — current model is fine, no noise
    if matched_profile is None:
        return {
            "task_type": "general",
            "task_label": "General conversation",
            "recommended_model_id": current_model_id,
            "recommended_model_display": MODELS.get(current_model_id, {}).get(
                "display", current_model_id
            ),
            "current_model_id": current_model_id,
            "current_is_optimal": True,
            "hard_requirement": False,
            "cannot_complete": False,
            "sidenotes": [],
        }

    preferred: list[str] = matched_profile["preferred_models"]
    hard_req: bool = matched_profile.get("hard_requirement", False)

    # ── Best configured model in priority order ───────────────────────────
    best_configured: str | None = next((m for m in preferred if m in configured_ids), None)

    # ── Hard requirement, no capable model configured → cannot complete ───
    if hard_req and best_configured is None:
        return {
            "task_type": matched_name,
            "task_label": matched_profile["label"],
            "recommended_model_id": None,
            "recommended_model_display": None,
            "current_model_id": current_model_id,
            "current_is_optimal": False,
            "hard_requirement": True,
            "cannot_complete": True,
            "sidenotes": [
                {
                    "model_id": mid,
                    "display": MODELS[mid]["display"],
                    "reason": matched_profile.get(
                        "hard_requirement_reason",
                        f"Required for {matched_profile['label']}",
                    ),
                }
                for mid in preferred[:2]
                if mid in MODELS
            ],
        }

    # ── Sidenotes: unconfigured models ranked higher than best_configured ─
    if best_configured:
        cutoff = preferred.index(best_configured)
        sidenotes = [
            {
                "model_id": mid,
                "display": MODELS[mid]["display"],
                "reason": f"Top choice for {matched_profile['label']} — add it in ⚙ API Keys",
            }
            for mid in preferred[:cutoff]
            if mid not in configured_ids and mid in MODELS
        ][:2]
    else:
        sidenotes = [
            {
                "model_id": mid,
                "display": MODELS[mid]["display"],
                "reason": f"Ideal for {matched_profile['label']} — add it in ⚙ API Keys",
            }
            for mid in preferred[:2]
            if mid in MODELS
        ]

    # ── Is current model already optimal? ────────────────────────────────
    current_rank = (
        preferred.index(current_model_id) if current_model_id in preferred else len(preferred)
    )
    best_rank = preferred.index(best_configured) if best_configured else len(preferred)
    current_is_optimal = (
        best_configured is None or best_configured == current_model_id or current_rank <= best_rank
    )

    recommended_id = best_configured or current_model_id
    result = {
        "task_type": matched_name,
        "task_label": matched_profile["label"],
        "recommended_model_id": recommended_id,
        "recommended_model_display": MODELS.get(recommended_id, {}).get("display", recommended_id),
        "current_model_id": current_model_id,
        "current_is_optimal": current_is_optimal,
        "hard_requirement": hard_req,
        "cannot_complete": False,
        "sidenotes": sidenotes,
    }
    if "profile_note" in matched_profile:
        result["profile_note"] = matched_profile["profile_note"]
    return result


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse(
    content: str = "", done: bool = False, event_type: str = "message", data: dict | None = None
) -> str:
    """Format a single SSE data frame."""
    if data:
        # Custom event with full data payload
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    else:
        # Standard message event
        return f"data: {json.dumps({'content': content, 'done': done})}\n\n"


# ---------------------------------------------------------------------------
# Provider: OpenAI
# ---------------------------------------------------------------------------


async def _stream_openai(
    model_id: str,
    system_prompt: str,
    history: list[dict],
    message: str,
    user_api_keys: dict | None = None,
) -> AsyncIterator[str]:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        yield _sse("[ERROR] openai package not installed. Run: pip install openai", done=True)
        return

    client = AsyncOpenAI(api_key=_resolve_api_key("OPENAI_API_KEY", "openai", user_api_keys))

    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    messages.append({"role": "user", "content": message})

    try:
        stream = await client.chat.completions.create(
            model=model_id,
            messages=messages,
            stream=True,
            max_tokens=2048,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield _sse(delta)
        yield _sse("", done=True)
    except Exception as exc:
        yield _sse(f"[ERROR] OpenAI: {exc}", done=True)


# ---------------------------------------------------------------------------
# Provider: Anthropic
# ---------------------------------------------------------------------------


async def _stream_anthropic(
    model_id: str,
    system_prompt: str,
    history: list[dict],
    message: str,
    user_api_keys: dict | None = None,
    tools: list[dict] | None = None,
) -> AsyncIterator[str]:
    try:
        import anthropic
    except ImportError:
        yield _sse("[ERROR] anthropic package not installed. Run: pip install anthropic", done=True)
        return

    client = anthropic.AsyncAnthropic(
        api_key=_resolve_api_key("ANTHROPIC_API_KEY", "anthropic", user_api_keys)
    )

    messages = list(history)
    messages.append({"role": "user", "content": message})

    try:
        # Build request params
        params: dict[str, Any] = {
            "model": model_id,
            "system": system_prompt,
            "messages": messages,
            "max_tokens": 2048,
        }

        # Add tools if provided
        if tools:
            params["tools"] = tools

        async with client.messages.stream(**params) as stream:
            async for event in stream:
                # Handle different event types
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        # Emit tool_use event to frontend
                        yield _sse(
                            event_type="tool_use",
                            data={
                                "tool_use_id": block.id,
                                "tool_name": block.name,
                                "tool_input": block.input,
                            },
                        )
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        # Stream text content
                        yield _sse(delta.text)
                    elif delta.type == "input_json_delta":
                        # Tool input is being streamed (we already sent tool_use event)
                        pass
                elif event.type == "message_stop":
                    # Check if we need to wait for tool results
                    final_message = await stream.get_final_message()
                    if final_message.stop_reason == "tool_use":
                        # Don't mark as done - frontend will send tool results
                        yield _sse(
                            event_type="tool_use_complete", data={"waiting_for_results": True}
                        )
                    else:
                        # Normal completion
                        yield _sse("", done=True)

        # If we exited without tool_use, mark as done
        yield _sse("", done=True)
    except Exception as exc:
        yield _sse(f"[ERROR] Anthropic: {exc}", done=True)


# ---------------------------------------------------------------------------
# Provider: Google (Gemini)
# ---------------------------------------------------------------------------


async def _stream_google(
    model_id: str,
    system_prompt: str,
    history: list[dict],
    message: str,
    user_api_keys: dict | None = None,
) -> AsyncIterator[str]:
    try:
        import google.generativeai as genai
    except ImportError:
        yield _sse(
            "[ERROR] google-generativeai package not installed. Run: pip install google-generativeai",
            done=True,
        )
        return

    genai.configure(api_key=_resolve_api_key("GOOGLE_API_KEY", "google", user_api_keys))
    model = genai.GenerativeModel(
        model_name=model_id,
        system_instruction=system_prompt,
    )

    google_history = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        google_history.append({"role": role, "parts": [msg["content"]]})

    try:
        chat = model.start_chat(history=google_history)
        response = await chat.send_message_async(message, stream=True)
        async for chunk in response:
            if chunk.text:
                yield _sse(chunk.text)
        yield _sse("", done=True)
    except Exception as exc:
        yield _sse(f"[ERROR] Google: {exc}", done=True)


# ---------------------------------------------------------------------------
# Provider: Mistral (OpenAI-compatible API — no extra package needed)
# ---------------------------------------------------------------------------


async def _stream_mistral(
    model_id: str,
    system_prompt: str,
    history: list[dict],
    message: str,
    user_api_keys: dict | None = None,
) -> AsyncIterator[str]:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        yield _sse("[ERROR] openai package not installed. Run: pip install openai", done=True)
        return

    api_key = _resolve_api_key("MISTRAL_API_KEY", "mistral", user_api_keys)
    client = AsyncOpenAI(base_url="https://api.mistral.ai/v1", api_key=api_key)

    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    messages.append({"role": "user", "content": message})

    try:
        stream = await client.chat.completions.create(
            model=model_id,
            messages=messages,
            stream=True,
            max_tokens=2048,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield _sse(delta)
        yield _sse("", done=True)
    except Exception as exc:
        yield _sse(f"[ERROR] Mistral: {exc}", done=True)


# ---------------------------------------------------------------------------
# Provider: Groq (OpenAI-compatible API — no extra package needed)
# ---------------------------------------------------------------------------


async def _stream_groq(
    model_id: str,
    system_prompt: str,
    history: list[dict],
    message: str,
    user_api_keys: dict | None = None,
) -> AsyncIterator[str]:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        yield _sse("[ERROR] openai package not installed. Run: pip install openai", done=True)
        return

    api_key = _resolve_api_key("GROQ_API_KEY", "groq", user_api_keys)
    client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)

    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    messages.append({"role": "user", "content": message})

    try:
        stream = await client.chat.completions.create(
            model=model_id,
            messages=messages,
            stream=True,
            max_tokens=2048,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield _sse(delta)
        yield _sse("", done=True)
    except Exception as exc:
        yield _sse(f"[ERROR] Groq: {exc}", done=True)


# ---------------------------------------------------------------------------
# Provider: OpenRouter (OpenAI-compatible gateway — 100+ models)
# ---------------------------------------------------------------------------


async def _stream_openrouter(
    model_id: str,
    system_prompt: str,
    history: list[dict],
    message: str,
    user_api_keys: dict | None = None,
) -> AsyncIterator[str]:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        yield _sse("[ERROR] openai package not installed. Run: pip install openai", done=True)
        return

    api_key = _resolve_api_key("OPENROUTER_API_KEY", "openrouter", user_api_keys)
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={"HTTP-Referer": "https://sovereign-ai-context.app"},
    )

    # Strip "openrouter/" namespace prefix before calling the API
    actual_model = (
        model_id[len("openrouter/") :] if model_id.startswith("openrouter/") else model_id
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    messages.append({"role": "user", "content": message})

    try:
        stream = await client.chat.completions.create(
            model=actual_model,
            messages=messages,
            stream=True,
            max_tokens=2048,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield _sse(delta)
        yield _sse("", done=True)
    except Exception as exc:
        yield _sse(f"[ERROR] OpenRouter: {exc}", done=True)


# ---------------------------------------------------------------------------
# Provider: xAI / Grok (OpenAI-compatible API)
# ---------------------------------------------------------------------------


async def _stream_xai(
    model_id: str,
    system_prompt: str,
    history: list[dict],
    message: str,
    user_api_keys: dict | None = None,
) -> AsyncIterator[str]:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        yield _sse("[ERROR] openai package not installed. Run: pip install openai", done=True)
        return

    api_key = _resolve_api_key("XAI_API_KEY", "xai", user_api_keys)
    client = AsyncOpenAI(base_url="https://api.x.ai/v1", api_key=api_key)

    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    messages.append({"role": "user", "content": message})

    try:
        stream = await client.chat.completions.create(
            model=model_id,
            messages=messages,
            stream=True,
            max_tokens=2048,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield _sse(delta)
        yield _sse("", done=True)
    except Exception as exc:
        yield _sse(f"[ERROR] xAI: {exc}", done=True)


# ---------------------------------------------------------------------------
# Provider: Ollama (local server — OpenAI-compatible, zero data egress)
# ---------------------------------------------------------------------------


async def _stream_ollama(
    model_id: str,
    system_prompt: str,
    history: list[dict],
    message: str,
    user_api_keys: dict | None = None,
) -> AsyncIterator[str]:
    """
    Stream from a local Ollama server.

    The model_id in the registry uses an "ollama/" prefix (e.g. "ollama/llama3.2")
    to namespace it. The prefix is stripped before calling the Ollama API.

    The "key" stored for this provider is the Ollama server base URL
    (e.g. "http://localhost:11434"). Any non-empty string is valid;
    Ollama itself does not require an API key.
    """
    try:
        from openai import AsyncOpenAI
    except ImportError:
        yield _sse("[ERROR] openai package not installed. Run: pip install openai", done=True)
        return

    base_url = (
        _resolve_api_key("OLLAMA_BASE_URL", "ollama", user_api_keys) or "http://localhost:11434"
    )
    client = AsyncOpenAI(
        base_url=f"{base_url.rstrip('/')}/v1",
        api_key="ollama",
    )

    actual_model = model_id[len("ollama/") :] if model_id.startswith("ollama/") else model_id

    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    messages.append({"role": "user", "content": message})

    try:
        stream = await client.chat.completions.create(
            model=actual_model,
            messages=messages,
            stream=True,
            max_tokens=2048,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield _sse(delta)
        yield _sse("", done=True)
    except Exception as exc:
        yield _sse(f"[ERROR] Ollama: {exc}. Is Ollama running at {base_url}?", done=True)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


async def stream_response(
    model_id: str,
    system_prompt: str,
    history: list[dict],
    message: str,
    user_api_keys: dict | None = None,
    enable_tools: bool = False,
) -> AsyncIterator[str]:
    """
    Route to the correct provider and stream SSE-formatted response tokens.

    Args:
        model_id: Model identifier (must be in MODELS registry)
        system_prompt: Full system prompt (vault context injected here)
        history: Prior conversation turns [{role, content}]
        message: Current user message
        user_api_keys: None = demo/testnet (env fallback), dict = user's own keys.
        enable_tools: If True, pass built-in tools to the AI (Pass/Drive/Mail/Calendar operations)

    Yields:
        SSE data frames: 'data: {"content": "token", "done": false}\\n\\n'
        Tool use events: 'event: tool_use\\ndata: {"tool_use_id": "...", "tool_name": "...", "tool_input": {...}}\\n\\n'
        Final frame: 'data: {"content": "", "done": true}\\n\\n'
    """
    meta = get_model_meta(model_id, user_api_keys=user_api_keys)
    provider = meta["provider"]

    # Get built-in tools if enabled
    tools = get_tool_definitions() if enable_tools else None

    if provider == "openai":
        async for chunk in _stream_openai(
            model_id, system_prompt, history, message, user_api_keys=user_api_keys
        ):
            yield chunk
    elif provider == "anthropic":
        async for chunk in _stream_anthropic(
            model_id, system_prompt, history, message, user_api_keys=user_api_keys, tools=tools
        ):
            yield chunk
    elif provider == "google":
        async for chunk in _stream_google(
            model_id, system_prompt, history, message, user_api_keys=user_api_keys
        ):
            yield chunk
    elif provider == "mistral":
        async for chunk in _stream_mistral(
            model_id, system_prompt, history, message, user_api_keys=user_api_keys
        ):
            yield chunk
    elif provider == "groq":
        async for chunk in _stream_groq(
            model_id, system_prompt, history, message, user_api_keys=user_api_keys
        ):
            yield chunk
    elif provider == "xai":
        async for chunk in _stream_xai(
            model_id, system_prompt, history, message, user_api_keys=user_api_keys
        ):
            yield chunk
    elif provider == "ollama":
        async for chunk in _stream_ollama(
            model_id, system_prompt, history, message, user_api_keys=user_api_keys
        ):
            yield chunk
    elif provider == "openrouter":
        async for chunk in _stream_openrouter(
            model_id, system_prompt, history, message, user_api_keys=user_api_keys
        ):
            yield chunk
    else:
        yield _sse(f"[ERROR] Unknown provider: {provider}", done=True)


async def generate_completion(
    model_id: str,
    system_prompt: str,
    message: str,
    user_api_keys: dict | None = None,
) -> str:
    """
    Non-streaming completion — used for auto session_state summary generation.
    Returns the full response text.
    """
    full = []
    async for chunk in stream_response(
        model_id, system_prompt, [], message, user_api_keys=user_api_keys
    ):
        if chunk.startswith("data: "):
            try:
                data = json.loads(chunk[6:])
                if not data.get("done") and data.get("content"):
                    full.append(data["content"])
            except Exception:
                pass
    return "".join(full)
