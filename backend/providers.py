"""Registry of supported LLM providers.

Most providers (OpenAI, Grok/xAI, Ollama, Unsloth) speak the OpenAI Chat
Completions API, so they share one client path with a provider-specific
``base_url``. Anthropic/Claude uses its own SDK. The registry is the single
source of truth for defaults and for the example metadata the settings UI shows.
"""

# mode: "openai" -> use the OpenAI SDK (with base_url); "anthropic" -> Claude SDK.
PROVIDER_REGISTRY = {
    "openai": {
        "label": "OpenAI",
        "mode": "openai",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3-mini"],
        "key_required": True,
        "key_example": "sk-proj-… (or sk-…)",
        "key_url": "https://platform.openai.com/api-keys",
        "base_url_editable": False,
    },
    "claude": {
        "label": "Anthropic (Claude)",
        "mode": "anthropic",
        "base_url": "https://api.anthropic.com",
        "default_model": "claude-opus-4-8",
        "models": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
        "key_required": True,
        "key_example": "sk-ant-api03-…",
        "key_url": "https://console.anthropic.com/settings/keys",
        "base_url_editable": False,
    },
    "grok": {
        "label": "xAI (Grok)",
        "mode": "openai",
        "base_url": "https://api.x.ai/v1",
        "default_model": "grok-3",
        "models": ["grok-3", "grok-3-mini", "grok-2-latest"],
        "key_required": True,
        "key_example": "xai-…",
        "key_url": "https://console.x.ai",
        "base_url_editable": True,
    },
    "ollama": {
        "label": "Ollama (local)",
        "mode": "openai",
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.1",
        "models": ["llama3.1", "qwen2.5", "mistral", "phi3"],
        "key_required": False,
        "key_example": "(no key — runs locally)",
        "key_url": "https://ollama.com/download",
        "base_url_editable": True,
    },
    "unsloth": {
        "label": "Unsloth (self-hosted, OpenAI-compatible)",
        "mode": "openai",
        "base_url": "http://localhost:8000/v1",
        "default_model": "unsloth/Meta-Llama-3.1-8B-Instruct",
        "models": ["unsloth/Meta-Llama-3.1-8B-Instruct", "unsloth/Qwen2.5-7B-Instruct"],
        "key_required": False,
        "key_example": "(optional — set if your server requires it)",
        "key_url": "https://docs.unsloth.ai",
        "base_url_editable": True,
    },
}

# Aliases accepted as provider names.
PROVIDER_ALIASES = {"anthropic": "claude", "xai": "grok"}


def canonical(provider: str) -> str:
    """Normalizes a provider name (lowercase + alias resolution)."""
    p = (provider or "").strip().lower()
    return PROVIDER_ALIASES.get(p, p)


def get(provider: str) -> dict:
    """Returns the registry entry for a provider, or None."""
    return PROVIDER_REGISTRY.get(canonical(provider))


def mode_of(provider: str) -> str:
    entry = get(provider)
    return entry["mode"] if entry else "openai"


def public_view(provider_id: str, entry: dict, *, active: str,
                configured: dict) -> dict:
    """UI-safe metadata for one provider — never includes the API key itself."""
    cfg = configured.get(provider_id, {})
    return {
        "id": provider_id,
        "label": entry["label"],
        "mode": entry["mode"],
        "base_url": cfg.get("base_url") or entry["base_url"],
        "base_url_default": entry["base_url"],
        "base_url_editable": entry["base_url_editable"],
        "model": cfg.get("model") or entry["default_model"],
        "default_model": entry["default_model"],
        "models": entry["models"],
        "key_required": entry["key_required"],
        "key_example": entry["key_example"],
        "key_url": entry["key_url"],
        "key_set": bool(cfg.get("api_key")),
        "is_active": provider_id == canonical(active),
    }
