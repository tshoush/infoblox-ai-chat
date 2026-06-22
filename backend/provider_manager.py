"""Runtime management of the active LLM provider and per-provider credentials.

Holds an API key / base_url / model per provider, can switch the active provider
at runtime (reconfiguring the shared LLMClient), and persists everything to a
gitignored JSON file so settings survive restarts. API keys are never returned
to the UI — only a `key_set` boolean.
"""
import json
import os
import threading

from backend import providers as registry

DEFAULT_STORE = "backend/providers.local.json"


class ProviderManager:
    def __init__(self, llm_client, store_path: str = DEFAULT_STORE):
        self.llm_client = llm_client
        self.store_path = store_path
        self.configs = {}
        self._client_cache = {}
        self._lock = threading.Lock()
        self.active = registry.canonical(llm_client.config.provider)

        # Seed the active provider from the env-derived config.
        self.configs[self.active] = {
            "api_key": llm_client.config.api_key,
            "base_url": llm_client.config.base_url,
            "model": llm_client.config.model,
        }
        self._load()
        self._apply_active()

    # --- persistence --------------------------------------------------------
    def _load(self) -> None:
        if not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Could not load provider store: {e}")
            return
        self.active = registry.canonical(data.get("active", self.active))
        for pid, cfg in (data.get("providers") or {}).items():
            pid = registry.canonical(pid)
            if registry.get(pid) and isinstance(cfg, dict):
                merged = {**self.configs.get(pid, {}),
                          **{k: v for k, v in cfg.items() if v is not None}}
                self.configs[pid] = merged

    def _save(self) -> None:
        try:
            with open(self.store_path, "w") as f:
                json.dump({"active": self.active, "providers": self.configs}, f, indent=2)
        except OSError as e:
            print(f"Could not save provider store: {e}")

    # --- state --------------------------------------------------------------
    def _apply_active(self) -> None:
        cfg = self.configs.get(self.active, {})
        self.llm_client.reconfigure(self.active, cfg.get("api_key"),
                                    cfg.get("base_url"), cfg.get("model"))

    def set_provider(self, provider: str, api_key=None, base_url=None,
                     model=None, activate: bool = True) -> dict:
        """Store a provider's settings and optionally make it the active provider."""
        pid = registry.canonical(provider)
        entry = registry.get(pid)
        if entry is None:
            raise ValueError(f"Unknown provider '{provider}'.")

        with self._lock:
            cfg = dict(self.configs.get(pid, {}))
            if api_key is not None:
                cfg["api_key"] = api_key or None
            if base_url is not None:
                cfg["base_url"] = base_url or None
            if model is not None:
                cfg["model"] = model or None
            self.configs[pid] = cfg
            self._client_cache.pop(pid, None)  # creds changed -> drop cached client

            if activate:
                if entry["key_required"] and not cfg.get("api_key"):
                    raise ValueError(f"{entry['label']} requires an API key.")
                self.active = pid
                self._apply_active()

            self._save()
            return self.public()

    def model_ids(self, base: str = "iaci-infoblox-wapi") -> list:
        """OpenAI-style model ids to advertise: the default plus one per usable
        provider (configured-with-key, or keyless). Lets OSS UIs switch provider
        via their native model dropdown (iaci-openai, iaci-claude, ...)."""
        ids = [base]
        for pid, entry in registry.PROVIDER_REGISTRY.items():
            cfg = self.configs.get(pid, {})
            if entry["key_required"] and not cfg.get("api_key"):
                continue  # hide providers that can't run yet
            ids.append(f"iaci-{pid}")
        return ids

    def client_for(self, provider: str):
        """Returns a (cached) LLMClient for `provider` using its stored creds,
        WITHOUT changing the active provider — safe for per-request routing.
        Returns None if the provider is unknown or missing a required key."""
        pid = registry.canonical(provider)
        entry = registry.get(pid)
        if entry is None:
            return None
        cfg = self.configs.get(pid, {})
        if entry["key_required"] and not cfg.get("api_key"):
            return None

        sig = (cfg.get("api_key"), cfg.get("base_url"), cfg.get("model"))
        with self._lock:
            cached = self._client_cache.get(pid)
            if cached and cached[0] == sig:
                return cached[1]

            import copy as _copy
            from backend.llm_client import LLMClient
            from backend.circuit_breaker import CircuitBreaker

            c = _copy.copy(self.llm_client.config)  # inherit timeout/max_tokens/etc.
            c.provider = pid
            c.api_key = cfg.get("api_key")
            c.base_url = cfg.get("base_url")
            c.model = cfg.get("model")
            client = LLMClient(c, self.llm_client.cache_manager, CircuitBreaker())
            self._client_cache[pid] = (sig, client)
            return client

    def public(self) -> dict:
        """UI-safe snapshot — no secrets, just whether each key is set."""
        return {
            "active": self.active,
            "providers": [
                registry.public_view(pid, entry, active=self.active, configured=self.configs)
                for pid, entry in registry.PROVIDER_REGISTRY.items()
            ],
        }

    # Substrings that mark a model as non-chat (so we hide them from the picker).
    _NON_CHAT = (
        "embedding", "whisper", "tts", "dall-e", "image", "moderation", "audio",
        "realtime", "search", "similarity", "babbage", "davinci", "ada-", "curie",
        "rerank", "clip", "transcribe", "vision-preview",
    )

    def _filter_models(self, models) -> list:
        out = [m for m in models if m and not any(t in m.lower() for t in self._NON_CHAT)]
        return sorted(set(out)) or sorted(set(models))

    def list_models(self, provider: str, api_key=None, base_url=None) -> dict:
        """Fetches the provider's live model list (its /v1/models or SDK list).

        Falls back to the registry's example models on any error so the UI always
        has something to show. Uses provided creds, else the stored ones.
        """
        pid = registry.canonical(provider)
        entry = registry.get(pid)
        if entry is None:
            raise ValueError(f"Unknown provider '{provider}'.")

        cfg = self.configs.get(pid, {})
        key = api_key or cfg.get("api_key")
        url = base_url or cfg.get("base_url") or entry["base_url"]
        if entry["key_required"] and not key:
            raise ValueError(f"{entry['label']} requires an API key to list models.")

        try:
            if entry["mode"] == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=key, timeout=15)
                models = [m.id for m in client.models.list().data]
            else:
                from openai import OpenAI
                client = OpenAI(api_key=key or "not-needed", base_url=url, timeout=15)
                models = [m.id for m in client.models.list().data]
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)[:200], "models": entry["models"], "source": "examples"}

        return {"ok": True, "models": self._filter_models(models), "source": "live"}

    def test(self) -> dict:
        """Sends a tiny prompt through the active provider to verify it works."""
        entry = registry.get(self.active)
        if entry and entry["key_required"] and not self.configs.get(self.active, {}).get("api_key"):
            return {"ok": False, "message": f"{entry['label']} has no API key set."}
        try:
            resp = self.llm_client.send_request(
                f"Reply with exactly one word: OK ({self.active})", use_cache=False)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)[:200]}
        if "error" in resp:
            return {"ok": False, "message": resp["error"][:200]}
        return {"ok": True, "message": (resp.get("content") or "").strip()[:80]}
