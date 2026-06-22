"""Opt-in live test that hits the real configured LLM provider (Claude).

Skipped by default so the suite stays offline and free. Enable with:

    RUN_LIVE_LLM=1 ./.venv/bin/python -m pytest backend/tests/test_live_llm.py -v -s

It uses the provider/key/model from your .env (currently provider=claude).
"""
import os

import pytest

from backend.config import load_config
from backend.cache import CacheManager
from backend.circuit_breaker import CircuitBreaker
from backend.llm_client import LLMClient

pytestmark = pytest.mark.live

LIVE = os.getenv("RUN_LIVE_LLM") in ("1", "true", "True")


@pytest.mark.skipif(not LIVE, reason="set RUN_LIVE_LLM=1 to run live LLM calls")
def test_real_llm_responds():
    cfg = load_config()
    client = LLMClient(cfg.llm, CacheManager(cfg.cache), CircuitBreaker())
    resp = client.send_request("Reply with exactly one word: PONG")
    assert "error" not in resp, resp
    assert "PONG" in resp.get("content", "").upper()
