"""
tests/test_api_chat.py — Tests for GET /chat/models and POST /chat/recommend

POST /chat/message (SSE streaming) is tested structurally but full stream
content is not asserted here — that's covered by integration tests.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SOVEREIGN_ENV", "testnet")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-that-is-long-enough-32b")
os.environ.setdefault("HEDERA_NETWORK", "testnet")
os.environ.setdefault("OPERATOR_ID", "0.0.1234")
os.environ.setdefault("OPERATOR_KEY", "302e020100300506032b657004220420" + "a" * 64)

from api.main import app # noqa: E402

client = TestClient(app)


# ── Session fixture ────────────────────────────────────────────────────────────

def _make_session(user_id: str = "", user_api_keys=None) -> MagicMock:
    """Build a mock Session with minimal required fields."""
    session = MagicMock()
    session.session_id = "test-session-id"
    session.token_id = "0.0.9999"
    session.serial = 1
    session.user_id = user_id
    session.user_api_keys = user_api_keys
    session.context_sections = {
        "harness": "I am your AI assistant.",
        "user": "Name: Test User",
        "config": "Be helpful.",
        "session_state": "Last session: test",
    }
    session.last_model = ""
    session.expired = False
    return session


# ── GET /chat/models ───────────────────────────────────────────────────────────

class TestListModels:
    def test_no_session_id_returns_env_models(self, monkeypatch):
        """No session_id → demo mode → returns models from env."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        res = client.get("/chat/models")
        assert res.status_code == 200
        data = res.json()
        assert "models" in data
        providers = {m["provider"] for m in data["models"]}
        assert "openai" in providers

    def test_no_env_keys_returns_empty_with_message(self, monkeypatch):
        """No env keys and no session → empty model list with guidance message."""
        for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
                    "MISTRAL_API_KEY", "GROQ_API_KEY", "OLLAMA_BASE_URL"]:
            monkeypatch.delenv(key, raising=False)
        res = client.get("/chat/models")
        assert res.status_code == 200
        data = res.json()
        assert data["models"] == []
        assert "message" in data

    def test_with_valid_session_uses_user_keys(self, monkeypatch):
        """Valid session → uses session.user_api_keys."""
        for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
                    "MISTRAL_API_KEY", "GROQ_API_KEY", "OLLAMA_BASE_URL"]:
            monkeypatch.delenv(key, raising=False)

        mock_session = _make_session(user_id="real-user", user_api_keys={"anthropic": "sk-ant-key"})

        with patch("api.routes.chat.get_session", return_value=mock_session):
            res = client.get("/chat/models?session_id=test-session-id")

        assert res.status_code == 200
        data = res.json()
        providers = {m["provider"] for m in data["models"]}
        assert providers == {"anthropic"}

    def test_expired_session_falls_back_to_env(self, monkeypatch):
        """Expired/invalid session → falls back to env keys."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with patch("api.routes.chat.get_session", return_value=None):
            res = client.get("/chat/models?session_id=expired-session-id")
            assert res.status_code == 200
            # Falls back to env keys — openai should appear
            providers = {m["provider"] for m in res.json()["models"]}
            assert "openai" in providers

    def test_byok_empty_keys_returns_no_models(self, monkeypatch):
        """User session with empty keys → empty model list with BYOK message."""
        for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
                    "MISTRAL_API_KEY", "GROQ_API_KEY", "OLLAMA_BASE_URL"]:
            monkeypatch.delenv(key, raising=False)

        mock_session = _make_session(user_id="real-user", user_api_keys={})

        with patch("api.routes.chat.get_session", return_value=mock_session):
            res = client.get("/chat/models?session_id=test-session-id")

        assert res.status_code == 200
        data = res.json()
        assert data["models"] == []
        assert "⚙" in data.get("message", "") # BYOK guidance mentions gear icon


# ── POST /chat/recommend ───────────────────────────────────────────────────────

class TestRecommend:
    def test_expired_session_returns_404(self):
        with patch("api.routes.chat.get_session", return_value=None):
            res = client.post("/chat/recommend", json={
                "session_id": "expired",
                "message": "write some code",
                "current_model": "gpt-4o",
            })
            assert res.status_code == 404

    def test_valid_session_returns_recommendation(self):
        mock_session = _make_session(user_api_keys={"openai": "sk-key"})
        with patch("api.routes.chat.get_session", return_value=mock_session):
            res = client.post("/chat/recommend", json={
                "session_id": "test-session-id",
                "message": "help me debug this python code",
                "current_model": "gpt-4o",
            })
            assert res.status_code == 200
            data = res.json()
            assert data["task_type"] == "coding"
            assert "recommended_model_id" in data
            assert "cannot_complete" in data

    def test_vision_task_cannot_complete_with_text_only(self):
        """Vision task with no multimodal model → cannot_complete True."""
        # Groq only — no vision capable model
        mock_session = _make_session(user_api_keys={"groq": "test-key"})
        with patch("api.routes.chat.get_session", return_value=mock_session):
            res = client.post("/chat/recommend", json={
                "session_id": "test-session-id",
                "message": "analyze this image for me",
                "current_model": "llama-3.3-70b-versatile",
            })
            assert res.status_code == 200
            assert res.json()["cannot_complete"] is True

    def test_general_message_returns_current_as_optimal(self):
        """Unclassified message → current model is optimal."""
        mock_session = _make_session(user_api_keys={"openai": "sk-key"})
        with patch("api.routes.chat.get_session", return_value=mock_session):
            res = client.post("/chat/recommend", json={
                "session_id": "test-session-id",
                "message": "hello, how are you?",
                "current_model": "gpt-4o",
            })
            assert res.status_code == 200
            assert res.json()["task_type"] == "general"
            assert res.json()["current_is_optimal"] is True

    def test_missing_field_returns_422(self):
        res = client.post("/chat/recommend", json={"session_id": "x", "message": "hi"})
        assert res.status_code == 422


# ── POST /chat/message ─────────────────────────────────────────────────────────

class TestChatMessage:
    def test_expired_session_returns_404(self):
        with patch("api.routes.chat.get_session", return_value=None):
            res = client.post("/chat/message", json={
                "session_id": "expired",
                "message": "hello",
                "model": "gpt-4o",
            })
            assert res.status_code == 404

    def test_empty_message_returns_400(self):
        mock_session = _make_session(user_api_keys=None)
        with patch("api.routes.chat.get_session", return_value=mock_session), \
                patch("api.routes.chat.get_model_meta", return_value={"provider": "openai", "env_key": "OPENAI_API_KEY", "display": "GPT-4o"}):
            res = client.post("/chat/message", json={
                "session_id": "test-session-id",
                "message": " ",
                "model": "gpt-4o",
            })
            assert res.status_code == 400
            assert "empty" in res.json()["detail"].lower()

    def test_unconfigured_model_returns_400(self):
        """Model not configured for user → 400."""
        mock_session = _make_session(user_api_keys={}) # no keys
        with patch("api.routes.chat.get_session", return_value=mock_session):
            res = client.post("/chat/message", json={
                "session_id": "test-session-id",
                "message": "hello",
                "model": "gpt-4o",
            })
            assert res.status_code == 400

    def test_unknown_model_returns_400(self):
        """Model ID not in registry → 400."""
        mock_session = _make_session(user_api_keys=None)
        with patch("api.routes.chat.get_session", return_value=mock_session):
            res = client.post("/chat/message", json={
                "session_id": "test-session-id",
                "message": "hello",
                "model": "does-not-exist-model",
            })
            assert res.status_code == 400

    def test_empty_context_sections_returns_409(self):
        """Session with no context sections → 409 (vault not loaded)."""
        mock_session = _make_session(user_api_keys=None)
        mock_session.context_sections = {} # empty vault
        with patch("api.routes.chat.get_session", return_value=mock_session):
            res = client.post("/chat/message", json={
                "session_id": "test-session-id",
                "message": "hello",
                "model": "gpt-4o",
            })
            assert res.status_code == 409

    def test_missing_required_fields_returns_422(self):
        res = client.post("/chat/message", json={"session_id": "x", "message": "hi"})
        assert res.status_code == 422


# ── build_system_prompt ────────────────────────────────────────────────────────

class TestBuildSystemPrompt:
    def test_sections_injected_in_canonical_order(self):
        """Sections appear in soul → user → symbiote → session_state order."""
        from api.routes.chat import build_system_prompt
        prompt = build_system_prompt(
            context_sections={"session_state": "state", "harness": "harness", "user": "user", "config": "cfg"},
            model_id="gpt-4o",
            token_id="0.0.1234",
        )
        soul_pos = prompt.index("=== HARNESS DIRECTIVES ===")
        user_pos = prompt.index("=== USER PROFILE ===")
        cfg_pos = prompt.index("=== AI CONFIGURATION ===")
        state_pos = prompt.index("=== SESSION CONTEXT ===")
        assert soul_pos < user_pos < cfg_pos < state_pos

    def test_token_id_in_footer(self):
        from api.routes.chat import build_system_prompt
        prompt = build_system_prompt({}, "gpt-4o", "0.0.5678")
        assert "0.0.5678" in prompt

    def test_empty_sections_no_section_labels(self):
        """Empty context sections → no section labels injected."""
        from api.routes.chat import build_system_prompt
        prompt = build_system_prompt({}, "gpt-4o", "0.0.1234")
        assert "=== HARNESS DIRECTIVES ===" not in prompt

    def test_unknown_sections_appended_at_end(self):
        """Unknown section names get added with their name uppercased."""
        from api.routes.chat import build_system_prompt
        prompt = build_system_prompt(
            {"harness": "soul text", "custom_section": "custom content"},
            "gpt-4o", "0.0.1234",
        )
        assert "=== CUSTOM_SECTION ===" in prompt
