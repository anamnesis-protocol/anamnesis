"""
tests/test_ai_router.py — Tests for api/services/ai_router.py

Tests available_models(), _resolve_api_key(), recommend_model(), and
the task profile classification logic. No real AI provider calls are made.
"""

import os
import pytest

os.environ.setdefault("SOVEREIGN_ENV", "testnet")

from api.services.ai_router import (
available_models,
recommend_model,
MODELS,
_TASK_PROFILES,
_resolve_api_key,
)


# ── _resolve_api_key ───────────────────────────────────────────────────────────

class TestResolveApiKey:
def test_none_keys_returns_env_value(self, monkeypatch):
"""user_api_keys=None → demo mode → reads from env."""
monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
result = _resolve_api_key("OPENAI_API_KEY", "openai", None)
assert result == "sk-env-key"

def test_none_keys_missing_env_returns_none(self, monkeypatch):
"""user_api_keys=None but env var not set → None."""
monkeypatch.delenv("OPENAI_API_KEY", raising=False)
result = _resolve_api_key("OPENAI_API_KEY", "openai", None)
assert result is None

def test_empty_dict_returns_none(self):
"""user_api_keys={} → real user with no keys → None for any provider."""
result = _resolve_api_key("OPENAI_API_KEY", "openai", {})
assert result is None

def test_dict_with_key_returns_user_key(self):
"""user_api_keys with value → returns that value, ignores env."""
result = _resolve_api_key("OPENAI_API_KEY", "openai", {"openai": "sk-user-key"})
assert result == "sk-user-key"

def test_dict_without_provider_returns_none(self):
"""user_api_keys present but provider missing → None (no env fallback)."""
result = _resolve_api_key("OPENAI_API_KEY", "openai", {"anthropic": "sk-ant-key"})
assert result is None


# ── available_models ───────────────────────────────────────────────────────────

class TestAvailableModels:
def test_demo_mode_no_env_keys_returns_empty(self, monkeypatch):
"""No env keys configured → no models available."""
for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
"MISTRAL_API_KEY", "GROQ_API_KEY", "OLLAMA_BASE_URL"]:
monkeypatch.delenv(key, raising=False)
result = available_models(user_api_keys=None)
assert result == []

def test_demo_mode_with_openai_key(self, monkeypatch):
"""OpenAI env key configured → returns only OpenAI models."""
for key in ["ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "MISTRAL_API_KEY",
"GROQ_API_KEY", "OLLAMA_BASE_URL"]:
monkeypatch.delenv(key, raising=False)
monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
result = available_models(user_api_keys=None)
providers = {m["provider"] for m in result}
assert providers == {"openai"}

def test_byok_empty_dict_returns_no_models(self):
"""Real user with empty keys dict → no models, no env fallback."""
result = available_models(user_api_keys={})
assert result == []

def test_byok_anthropic_key_returns_anthropic_only(self, monkeypatch):
"""User configured only anthropic key → only anthropic models."""
# Ensure env keys don't interfere
for key in ["OPENAI_API_KEY", "GOOGLE_API_KEY", "MISTRAL_API_KEY",
"GROQ_API_KEY", "OLLAMA_BASE_URL"]:
monkeypatch.delenv(key, raising=False)
result = available_models(user_api_keys={"anthropic": "sk-ant-test"})
assert len(result) > 0
providers = {m["provider"] for m in result}
assert providers == {"anthropic"}

def test_byok_multiple_providers(self):
"""Multiple providers in user keys → all their models shown."""
result = available_models(user_api_keys={
"openai": "sk-openai",
"google": "goog-key",
})
providers = {m["provider"] for m in result}
assert "openai" in providers
assert "google" in providers
assert "anthropic" not in providers

def test_result_has_required_fields(self, monkeypatch):
"""Each model dict has id, display, provider fields."""
monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
result = available_models(user_api_keys=None)
for model in result:
assert "id" in model
assert "display" in model
assert "provider" in model


# ── recommend_model ────────────────────────────────────────────────────────────

class TestRecommendModel:
# All user keys available
ALL_KEYS = {m_meta["provider"]: "test-key" for m_meta in MODELS.values()}

def test_general_query_returns_current_model_as_optimal(self):
"""Unclassified message → current model is optimal, no switch."""
result = recommend_model("hello", "gpt-4o", self.ALL_KEYS)
assert result["task_type"] == "general"
assert result["current_is_optimal"] is True
assert result["cannot_complete"] is False

def test_coding_query_detected(self):
"""Message with 'code' keyword → classified as coding."""
result = recommend_model("write a python function to sort a list", "gpt-4o", self.ALL_KEYS)
assert result["task_type"] == "coding"
assert result["task_label"] == "Code generation / debugging"

def test_vision_query_detected(self):
"""Message with 'image' keyword → classified as vision."""
result = recommend_model("analyze this image for me", "gpt-4o", self.ALL_KEYS)
assert result["task_type"] == "vision"
assert result["hard_requirement"] is True

def test_vision_no_capable_model_cannot_complete(self):
"""Vision task with no multimodal model → cannot_complete."""
text_only_keys = {"anthropic": "key", "mistral": "key"}
result = recommend_model("look at this image", "claude-3-5-sonnet-20241022", text_only_keys)
# Claude does support vision — use a model that doesn't
# Use groq-only to test cannot_complete
groq_only = {"groq": "key"}
result = recommend_model("describe what's in this photo", "llama-3.3-70b-versatile", groq_only)
assert result["task_type"] == "vision"
assert result["cannot_complete"] is True
assert result["recommended_model_id"] is None
assert len(result["sidenotes"]) > 0

def test_privacy_query_routes_to_ollama(self):
"""Message with 'confidential' → privacy profile → Ollama preferred."""
result = recommend_model(
"this is confidential company data, analyze it",
"gpt-4o",
{**self.ALL_KEYS, "ollama": "http://localhost:11434"},
)
assert result["task_type"] == "privacy"
assert result["recommended_model_id"].startswith("ollama/")

def test_sidenotes_surface_unconfigured_preferred_models(self):
"""Best preferred model not configured → appears in sidenotes."""
# Vision task prefers gpt-4o first, but user only has anthropic
anthropic_only = {"anthropic": "sk-ant-key"}
result = recommend_model("can you see this image?", "claude-3-5-sonnet-20241022", anthropic_only)
# gpt-4o is ranked higher for vision — should appear in sidenotes
sidenote_ids = [s["model_id"] for s in result.get("sidenotes", [])]
assert "gpt-4o" in sidenote_ids

def test_current_model_optimal_no_sidenotes(self):
"""Current model IS the best configured option → current_is_optimal True."""
openai_only = {"openai": "sk-key"}
result = recommend_model("write me a python function", "gpt-4o", openai_only)
assert result["current_is_optimal"] is True

def test_reasoning_query_detected(self):
"""'analyze' keyword → reasoning task."""
result = recommend_model("analyze the pros and cons of this approach", "gpt-4o", self.ALL_KEYS)
assert result["task_type"] == "reasoning"

def test_fast_query_detected(self):
"""'quick question' keyword → fast task."""
result = recommend_model("quick question: what is the capital of France?", "gpt-4o", self.ALL_KEYS)
assert result["task_type"] == "fast"

def test_empty_keys_returns_sidenotes_not_errors(self):
"""Empty user keys dict → all soft tasks return general or sidenotes, no crash."""
result = recommend_model("write me some code", "gpt-4o", {})
# Should not raise — returns result with no recommended model available
assert "task_type" in result
assert "cannot_complete" in result

def test_response_has_all_required_fields(self):
"""recommend_model always returns all required fields."""
result = recommend_model("hello world", "gpt-4o", self.ALL_KEYS)
required = [
"task_type", "task_label", "recommended_model_id",
"recommended_model_display", "current_model_id",
"current_is_optimal", "hard_requirement",
"cannot_complete", "sidenotes",
]
for field in required:
assert field in result, f"Missing field: {field}"

def test_unknown_current_model_does_not_crash(self):
"""Unknown model_id in current_model_id → handled gracefully."""
result = recommend_model("hello", "some-unknown-model-id", self.ALL_KEYS)
assert result["current_model_id"] == "some-unknown-model-id"


# ── Task profile registry sanity checks ───────────────────────────────────────

class TestTaskProfiles:
def test_all_profiles_have_required_keys(self):
"""Every task profile has keywords, preferred_models, hard_requirement."""
for name, profile in _TASK_PROFILES.items():
assert "keywords" in profile, f"{name} missing keywords"
assert "preferred_models" in profile, f"{name} missing preferred_models"
assert "hard_requirement" in profile, f"{name} missing hard_requirement"

def test_preferred_models_exist_in_registry(self):
"""Every preferred model in every profile is in the MODELS registry."""
for name, profile in _TASK_PROFILES.items():
for model_id in profile["preferred_models"]:
assert model_id in MODELS, f"{name} references unknown model: {model_id}"

def test_vision_has_hard_requirement(self):
"""Vision profile must mark hard_requirement True."""
assert _TASK_PROFILES["vision"]["hard_requirement"] is True

def test_privacy_profile_prefers_ollama(self):
"""Privacy profile's first preferred model should be an Ollama model."""
first = _TASK_PROFILES["privacy"]["preferred_models"][0]
assert first.startswith("ollama/"), f"Expected Ollama first, got {first}"
