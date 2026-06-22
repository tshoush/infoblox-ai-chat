"""Tests for the LLM provider registry and runtime manager."""
import json

import pytest

from backend import providers as registry
from backend.provider_manager import ProviderManager


class FakeLLMClient:
    """Stands in for LLMClient: records reconfigure() calls and carries the real
    config/cache/breaker so ProviderManager.client_for() can build sub-clients."""

    def __init__(self):
        from backend.config import LLMConfig, CacheConfig
        from backend.cache import CacheManager
        from backend.circuit_breaker import CircuitBreaker
        self.config = LLMConfig(provider="claude", api_key="seed-key")
        self.cache_manager = CacheManager(CacheConfig(enable_cache=False))
        self.circuit_breaker = CircuitBreaker()
        self.reconfigured = []

    def reconfigure(self, provider, api_key=None, base_url=None, model=None):
        self.config.provider = provider
        self.config.api_key = api_key
        self.config.base_url = base_url
        self.config.model = model
        self.reconfigured.append((provider, api_key, base_url, model))

    def send_request(self, prompt, context=None, use_cache=True):
        return {"content": "OK"}


def _manager(tmp_path):
    return ProviderManager(FakeLLMClient(), store_path=str(tmp_path / "providers.json"))


# --- registry --------------------------------------------------------------

def test_registry_has_expected_providers():
    for pid in ("openai", "claude", "grok", "ollama", "unsloth"):
        assert registry.get(pid) is not None


def test_aliases_resolve():
    assert registry.canonical("anthropic") == "claude"
    assert registry.canonical("xai") == "grok"
    assert registry.canonical("OpenAI") == "openai"


def test_public_view_masks_key():
    view = registry.public_view("openai", registry.get("openai"),
                                active="openai", configured={"openai": {"api_key": "sk-secret"}})
    assert view["key_set"] is True
    assert "api_key" not in view  # never leak the key
    assert view["is_active"] is True
    assert "gpt-4o" in view["models"]


# --- manager ---------------------------------------------------------------

def test_public_list_lists_all_with_active(tmp_path):
    mgr = _manager(tmp_path)
    pub = mgr.public()
    ids = {p["id"] for p in pub["providers"]}
    assert {"openai", "claude", "grok", "ollama", "unsloth"} <= ids
    assert pub["active"] == "claude"


def test_set_provider_activates_and_reconfigures(tmp_path):
    mgr = _manager(tmp_path)
    mgr.set_provider("grok", api_key="xai-abc", model="grok-3")
    assert mgr.active == "grok"
    assert mgr.llm_client.reconfigured[-1] == ("grok", "xai-abc", None, "grok-3")


def test_set_provider_requires_key_when_required(tmp_path):
    mgr = _manager(tmp_path)
    with pytest.raises(ValueError, match="requires an API key"):
        mgr.set_provider("openai", api_key="")  # openai needs a key


def test_keyless_provider_activates_without_key(tmp_path):
    mgr = _manager(tmp_path)
    mgr.set_provider("ollama", base_url="http://localhost:11434/v1", model="llama3.1")
    assert mgr.active == "ollama"


def test_filter_models_drops_non_chat(tmp_path):
    mgr = _manager(tmp_path)
    models = ["gpt-4o", "text-embedding-3-large", "whisper-1", "gpt-4o-mini",
              "dall-e-3", "tts-1", "o3-mini"]
    kept = mgr._filter_models(models)
    assert "gpt-4o" in kept and "gpt-4o-mini" in kept and "o3-mini" in kept
    assert "text-embedding-3-large" not in kept
    assert "whisper-1" not in kept and "dall-e-3" not in kept and "tts-1" not in kept


def test_list_models_requires_key_for_keyed_provider(tmp_path):
    mgr = _manager(tmp_path)
    with pytest.raises(ValueError, match="requires an API key"):
        mgr.list_models("grok")  # no key stored or provided


def test_list_models_falls_back_to_examples_on_error(tmp_path, monkeypatch):
    mgr = _manager(tmp_path)
    # ollama needs no key; the SDK call will fail (nothing listening) -> examples.
    result = mgr.list_models("ollama")
    assert result["models"]  # never empty
    assert result["source"] in ("live", "examples")


def test_model_ids_advertises_default_plus_usable_providers(tmp_path):
    mgr = _manager(tmp_path)  # active=claude (key set), ollama keyless
    ids = mgr.model_ids()
    assert "iaci-infoblox-wapi" in ids
    assert "iaci-claude" in ids       # has a key
    assert "iaci-ollama" in ids       # keyless -> usable
    assert "iaci-openai" not in ids   # needs a key, not set
    # After adding an OpenAI key it appears.
    mgr.set_provider("openai", api_key="sk-test", activate=False)
    assert "iaci-openai" in mgr.model_ids()


def test_client_for_returns_none_without_required_key(tmp_path):
    mgr = _manager(tmp_path)
    assert mgr.client_for("grok") is None  # no key configured


def test_client_for_builds_client_for_keyless_provider(tmp_path):
    mgr = _manager(tmp_path)
    mgr.set_provider("ollama", base_url="http://localhost:11434/v1", activate=False)
    client = mgr.client_for("ollama")
    assert client is not None
    assert client.config.provider == "ollama"
    # Cached on second call (same signature).
    assert mgr.client_for("ollama") is client
    # Building the ollama sub-client must NOT change the active provider.
    assert mgr.active == "claude"


def test_settings_persist_to_disk(tmp_path):
    store = tmp_path / "providers.json"
    mgr = ProviderManager(FakeLLMClient(), store_path=str(store))
    mgr.set_provider("grok", api_key="xai-xyz")
    saved = json.loads(store.read_text())
    assert saved["active"] == "grok"
    assert saved["providers"]["grok"]["api_key"] == "xai-xyz"

    # A fresh manager reloads the persisted active provider.
    mgr2 = ProviderManager(FakeLLMClient(), store_path=str(store))
    assert mgr2.active == "grok"
