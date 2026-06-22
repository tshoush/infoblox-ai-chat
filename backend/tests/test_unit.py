"""Hermetic unit tests for the IACI backend (no network, no Redis required).

These also serve as regression tests for the startup/runtime bugs fixed on
2026-06-19 (missing typing import, unconditional ollama import, bad
llm_cache_ttl reference, eager RAG/OpenAI requirement).
"""
from unittest.mock import MagicMock

import pytest

from backend.config import LLMConfig, CacheConfig, load_config
from backend.cache import CacheManager
from backend.circuit_breaker import CircuitBreaker
from backend.vocabulary import Vocabulary
from backend.llm_client import LLMClient
from backend.ai_processor import AIProcessor


# --- imports / regression for crash-on-import bugs -------------------------

def test_modules_import_cleanly():
    """cache.py used `Any` unimported; llm_client imported ollama unconditionally."""
    import backend.cache  # noqa: F401
    import backend.llm_client  # noqa: F401


def test_config_loads_from_env():
    cfg = load_config()
    assert cfg.infoblox is not None
    assert cfg.llm.provider  # set in .env


def test_config_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "definitely-not-a-provider")
    with pytest.raises(ValueError, match="not supported"):
        load_config()


def test_config_rejects_out_of_range_temperature(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "5.0")
    with pytest.raises(ValueError, match="LLM_TEMPERATURE"):
        load_config()


def test_config_rejects_nonpositive_max_tokens(monkeypatch):
    monkeypatch.setenv("LLM_MAX_TOKENS", "0")
    with pytest.raises(ValueError, match="LLM_MAX_TOKENS"):
        load_config()


# --- cache -----------------------------------------------------------------

def test_cache_without_redis_is_graceful():
    cache = CacheManager(CacheConfig(enable_cache=False))
    assert cache.get("missing") is None
    cache.set("k", {"v": 1})  # no-op, must not raise
    assert isinstance(cache.generate_session_id(), str)
    assert cache.get_session_data("s") == {}


# --- circuit breaker -------------------------------------------------------

def test_circuit_breaker_returns_value_on_success():
    cb = CircuitBreaker()
    assert cb.call(lambda: 42) == 42


def test_circuit_breaker_opens_after_failures():
    cb = CircuitBreaker(failure_threshold=1, max_retries=0, initial_backoff=0)

    def boom():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        cb.call(boom)
    assert cb.state == "open"


def test_circuit_breaker_fails_fast_when_open():
    """While open and within the cooldown, calls are rejected without invoking func."""
    from backend.circuit_breaker import CircuitOpenError

    cb = CircuitBreaker(failure_threshold=1, max_retries=0, initial_backoff=0, recovery_timeout=999)
    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert cb.state == "open"

    calls = []
    with pytest.raises(CircuitOpenError):
        cb.call(lambda: calls.append(1))
    assert calls == []  # func was never called


def test_circuit_breaker_half_open_recovers():
    cb = CircuitBreaker(failure_threshold=1, max_retries=0, initial_backoff=0, recovery_timeout=0)
    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert cb.state == "open"
    # recovery_timeout=0 -> immediately eligible for a half-open trial that succeeds.
    assert cb.call(lambda: "ok") == "ok"
    assert cb.state == "closed"


def test_circuit_breaker_counts_one_failure_per_call():
    """Retries within a single call must count as ONE failure, not one each."""
    cb = CircuitBreaker(failure_threshold=2, max_retries=2, initial_backoff=0)

    def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        cb.call(boom)
    assert cb.failure_count == 1 and cb.state == "closed"  # below threshold
    with pytest.raises(RuntimeError):
        cb.call(boom)
    assert cb.state == "open"  # second logical failure trips it


def test_circuit_breaker_retries_then_succeeds():
    cb = CircuitBreaker(failure_threshold=5, max_retries=2, initial_backoff=0)
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return "recovered"

    assert cb.call(flaky) == "recovered"
    assert attempts["n"] == 3


# --- vocabulary ------------------------------------------------------------

def test_vocabulary_add_and_get_roundtrip(tmp_path):
    vocab = Vocabulary(file_path=str(tmp_path / "vocab.json"))
    vocab.add_terms(["network", "record:a"], "wapi_objects")
    assert "network" in vocab.get_terms("wapi_objects")
    assert vocab.validate_entity("record:a", "wapi_objects")
    assert not vocab.validate_entity("nope", "wapi_objects")


# --- LLM client (mocked anthropic) -----------------------------------------

def _mocked_claude_client():
    llm_cfg = LLMConfig(provider="claude", api_key="test-key", model="claude-x")
    cache = CacheManager(CacheConfig(enable_cache=False))
    client = LLMClient(llm_cfg, cache, CircuitBreaker())
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="PONG")]
    client.anthropic_client = MagicMock()
    client.anthropic_client.messages.create.return_value = fake_response
    return client


def test_llm_client_parses_claude_response():
    client = _mocked_claude_client()
    assert client.send_request("ping") == {"content": "PONG"}


def test_llm_client_cache_response_does_not_crash():
    """Regression: cache_response referenced a non-existent LLMConfig.llm_cache_ttl."""
    client = _mocked_claude_client()
    client.cache_response("prompt", {"content": "x"})  # must not raise


# --- AI processor ----------------------------------------------------------

def _processor(send_return):
    llm = MagicMock()
    llm.format_prompt.return_value = "prompt"
    llm.send_request.return_value = send_return
    rag = MagicMock()
    rag.retrieve_context.return_value = []
    return AIProcessor(llm, rag, MagicMock())


def test_process_query_text_response():
    out = _processor({"content": "hello there"}).process_query("hi")
    assert out == {"response_type": "text", "content": "hello there"}


def test_process_query_api_call_proposal():
    payload = '{"operation": "search", "method": "GET", "parameters": {}}'
    out = _processor({"content": payload}).process_query("find networks")
    assert out["response_type"] == "api_call_proposal"
    assert out["proposal"]["method"] == "GET"


def test_process_query_falls_back_on_llm_error():
    out = _processor({"error": "boom"}).process_query("hi")
    assert out["response_type"] == "text"
    assert "Fallback" in out["content"]


def test_process_query_parses_fenced_json_proposal():
    """LLMs commonly wrap JSON in a ```json fence; it must still be recognised."""
    payload = '```json\n{"operation": "network", "method": "GET", "parameters": {}}\n```'
    out = _processor({"content": payload}).process_query("find networks")
    assert out["response_type"] == "api_call_proposal"
    assert out["proposal"]["operation"] == "network"


def test_process_query_parses_json_embedded_in_prose():
    payload = 'Sure! Here is the call:\n{"operation": "record:a", "method": "POST", "parameters": {"name": "x"}}\nLet me know.'
    out = _processor({"content": payload}).process_query("create a record")
    assert out["response_type"] == "api_call_proposal"
    assert out["proposal"]["method"] == "POST"


def test_extract_json_returns_none_for_plain_text():
    assert AIProcessor._extract_json("just a friendly sentence") is None
    assert AIProcessor._extract_json("") is None


def test_process_query_multi_step_plan():
    payload = (
        '{"operations": ['
        '{"operation": "network", "method": "POST", "parameters": {"network": "10.9.0.0/24"}},'
        '{"operation": "range", "method": "POST", "parameters": {"network": "10.9.0.0/24", '
        '"start_addr": "10.9.0.100", "end_addr": "10.9.0.200"}}]}'
    )
    out = _processor({"content": payload}).process_query("create a network and a dhcp scope")
    assert out["response_type"] == "api_call_plan"
    assert len(out["operations"]) == 2
    assert out["operations"][0]["operation"] == "network"
    assert out["operations"][1]["operation"] == "range"


def test_process_query_single_op_plan_collapses_to_proposal():
    payload = '{"operations": [{"operation": "network", "method": "GET", "parameters": {}}]}'
    out = _processor({"content": payload}).process_query("list networks")
    assert out["response_type"] == "api_call_proposal"
    assert out["proposal"]["operation"] == "network"


def test_process_query_bare_array_plan():
    payload = (
        '[{"operation": "network", "method": "POST", "parameters": {"network": "10.1.0.0/24"}},'
        '{"operation": "range", "method": "POST", "parameters": {"network": "10.1.0.0/24"}}]'
    )
    out = _processor({"content": payload}).process_query("make a net and scope")
    assert out["response_type"] == "api_call_plan"
    assert len(out["operations"]) == 2


def test_revise_plan_applies_amendment():
    revised = '{"operations": [{"operation": "network", "method": "POST", "parameters": {"network": "10.1.0.0/24", "options": [{"name": "routers", "num": 3, "value": "10.1.0.254"}]}}]}'
    proc = _processor({"content": revised})
    pending = [{"operation": "network", "method": "POST", "parameters": {"network": "10.1.0.0/24"}}]
    out = proc.revise_plan(pending, "change the gateway to .254")
    assert out[0]["parameters"]["options"][0]["value"] == "10.1.0.254"


def test_revise_plan_returns_none_for_conversational_reply():
    proc = _processor({"content": "Sure, what would you like to change?"})
    out = proc.revise_plan([{"operation": "network", "method": "POST", "parameters": {}}], "hmm")
    assert out is None
