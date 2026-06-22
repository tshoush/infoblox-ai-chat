import json
from typing import Any, Dict, List, Optional

from openai import OpenAI
import anthropic

from backend.config import LLMConfig
from backend.circuit_breaker import CircuitBreaker
from backend.cache import CacheManager
from backend import providers as provider_registry

class LLMClient:
    """Talks to any registered LLM provider.

    OpenAI-compatible providers (openai, grok, ollama, unsloth) share the OpenAI
    SDK with a provider-specific ``base_url``; Anthropic/Claude uses its own SDK.
    The active provider can be swapped at runtime via :meth:`reconfigure`.
    """

    def __init__(self, config: LLMConfig, cache_manager: CacheManager, circuit_breaker: CircuitBreaker):
        self.config = config
        self.cache_manager = cache_manager
        self.circuit_breaker = circuit_breaker
        self.openai_client = None
        self.anthropic_client = None
        self.mode = "openai"
        self._build_clients()

    def _build_clients(self) -> None:
        """(Re)creates the underlying SDK client for the current provider."""
        entry = provider_registry.get(self.config.provider)
        if entry is None:
            raise ValueError(f"Unsupported LLM provider: {self.config.provider}")
        self.mode = entry["mode"]
        self.openai_client = None
        self.anthropic_client = None
        if self.mode == "anthropic":
            self.anthropic_client = anthropic.Anthropic(
                api_key=self.config.api_key, timeout=self.config.timeout)
        else:
            self.openai_client = OpenAI(
                api_key=self.config.api_key or "not-needed",
                base_url=self.config.base_url or entry["base_url"],
                timeout=self.config.timeout,
            )

    def reconfigure(self, provider: str, api_key: Optional[str] = None,
                    base_url: Optional[str] = None, model: Optional[str] = None) -> None:
        """Switch the active provider/credentials/model at runtime."""
        self.config.provider = provider
        self.config.api_key = api_key
        self.config.base_url = base_url
        self.config.model = model
        self._build_clients()

    def _default_model(self) -> Optional[str]:
        entry = provider_registry.get(self.config.provider)
        return entry["default_model"] if entry else None

    def send_request(self, prompt: str, context: Optional[str] = None,
                     use_cache: bool = True) -> Dict[str, Any]:
        """Sends a request to the configured LLM provider."""
        if use_cache:
            cached_response = self.get_cached_response(prompt)
            if cached_response:
                return cached_response

        try:
            handler = self._claude_chat_completion if self.mode == "anthropic" else self._openai_chat_completion
            response = self.circuit_breaker.call(handler, prompt=prompt, context=context)
            parsed_response = self.parse_response(response)
            if use_cache:
                self.cache_response(prompt, parsed_response)
            return parsed_response
        except Exception as e:
            self.handle_provider_failure(e)
            return {"error": str(e)}

    def _claude_chat_completion(self, prompt: str, context: Optional[str] = None) -> Any:
        kwargs = {
            "model": self.config.model or self._default_model() or "claude-opus-4-8",
            "max_tokens": self.config.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if context:
            kwargs["system"] = context
        # NOTE: newer Claude models (opus-4.x) reject `temperature` entirely, so
        # it is intentionally omitted here. OpenAI-mode paths still honor it.

        return self.anthropic_client.messages.create(**kwargs)

    def _openai_chat_completion(self, prompt: str, context: Optional[str] = None) -> Any:
        """Shared path for all OpenAI-compatible providers (openai, grok,
        ollama, unsloth) — only the client's base_url/key differ."""
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})

        return self.openai_client.chat.completions.create(
            model=self.config.model or self._default_model() or "gpt-4o",
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

    def format_prompt(self, query: str, context: Optional[str] = None, tools_schema: Optional[Dict] = None) -> str:
        """Creates an optimized prompt for WAPI operations.

        When a tools schema is supplied, instruct the model to emit a strict JSON
        object describing the WAPI call. The shape must match what
        ``AIProcessor`` and ``WapiClient`` expect:
          - ``operation``: the WAPI object *type* (e.g. "network", "record:a"),
            NOT a sentence.
          - ``method``: one of GET, POST, PUT, DELETE.
          - ``parameters``: query params (GET) or the object body (POST/PUT).
          - ``ref`` (optional): the object _ref, required for PUT/DELETE.
        """
        prompt_parts = []
        if context and context.strip():
            prompt_parts.append(f"Context:\n{context.strip()}\n")
        prompt_parts.append(f"User request: {query}")

        if tools_schema:
            prompt_parts.append(
                "\nAvailable WAPI objects and fields:\n" + json.dumps(tools_schema, indent=2)
            )
            prompt_parts.append(
                "\nRespond with ONLY JSON (no prose, no markdown fences).\n"
                "A single WAPI call is an object of this exact shape:\n"
                '{"operation": "<wapi_object_type>", "method": "GET|POST|PUT|DELETE", '
                '"parameters": { }, "ref": "<optional object _ref for PUT/DELETE>"}\n'
                'Rules: "operation" MUST be a WAPI object type such as "network" or "record:a" '
                '(never a sentence). Use GET to search/list, POST to create, PUT to modify, '
                "DELETE to remove. Put search filters or new field values in \"parameters\".\n"
                'Example — "list all networks" -> '
                '{"operation": "network", "method": "GET", "parameters": {}}\n'
                "\nIf the request needs SEVERAL ordered calls, return "
                '{"operations": [call1, call2, ...]} where each element has the shape above and '
                "the calls are listed in execution order (earlier objects may be prerequisites of later ones).\n"
                "DHCP guidance: a network is the `network` object; a DHCP scope/pool is a `range` object "
                "(fields start_addr, end_addr, network); DHCP options go in an `options` array on the "
                'network or range, each like {"name":"routers","num":3,"value":"10.0.0.1"}, '
                '{"name":"domain-name-servers","num":6,"value":"8.8.8.8"}, '
                '{"name":"domain-name","num":15,"value":"example.com"}.\n'
                'Example — "create network 10.9.0.0/24 with a DHCP pool .100-.200, gateway .1 and DNS 8.8.8.8" ->\n'
                '{"operations": ['
                '{"operation": "network", "method": "POST", "parameters": {"network": "10.9.0.0/24", '
                '"options": [{"name": "routers", "num": 3, "value": "10.9.0.1"}, '
                '{"name": "domain-name-servers", "num": 6, "value": "8.8.8.8"}]}}, '
                '{"operation": "range", "method": "POST", "parameters": {"network": "10.9.0.0/24", '
                '"start_addr": "10.9.0.100", "end_addr": "10.9.0.200"}}]}\n'
                "If the request is not a WAPI operation, reply in plain natural language instead."
            )
        return "\n".join(prompt_parts)

    def parse_response(self, response: Any) -> Dict[str, Any]:
        """Extracts structured data from LLM responses."""
        if self.mode == "anthropic":
            return {"content": response.content[0].text}
        # OpenAI-compatible (openai, grok, ollama, unsloth)
        return {"content": response.choices[0].message.content}

    def handle_provider_failure(self, error: Exception) -> None:
        """Implements fallback and retry logic for provider failures."""
        print(f"LLM provider failure: {error}")
        if self.config.fallback_enabled:
            # Implement more sophisticated fallback (e.g., switch to another provider)
            pass

    def _cache_key(self, prompt: str) -> str:
        # Hash the (potentially multi-KB) prompt + provider/model so the Redis key
        # stays small and is scoped to the model that produced the answer.
        import hashlib
        h = hashlib.sha256(f"{self.config.provider}|{self.config.model}|{prompt}".encode()).hexdigest()
        return f"llm_cache:{h}"

    def cache_response(self, prompt: str, response: Dict[str, Any]) -> None:
        """Caches successful responses."""
        # CacheManager.set falls back to its configured llm_cache_ttl when ttl is None.
        self.cache_manager.set(self._cache_key(prompt), response)

    def get_cached_response(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Retrieves cached responses."""
        return self.cache_manager.get(self._cache_key(prompt))
