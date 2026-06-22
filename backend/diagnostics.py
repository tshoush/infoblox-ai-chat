"""Standalone connectivity diagnostics for the IACI backend.

These are operational smoke checks, NOT pytest tests (the module is named so
pytest will not collect it, and the functions do not start with ``test_``).

Run from the repo root:

    python -m backend.diagnostics            # check both Infoblox and the LLM
    python -m backend.diagnostics infoblox   # check only the Grid connection
    python -m backend.diagnostics llm        # check only the LLM provider
"""
import sys

import requests

from backend.config import load_config
from backend.cache import CacheManager
from backend.circuit_breaker import CircuitBreaker
from backend.llm_client import LLMClient


def check_infoblox_connection() -> bool:
    """Verifies connectivity to the Infoblox Grid Master."""
    try:
        cfg = load_config().infoblox
        url = f"https://{cfg.grid_ip}/wapi/{cfg.wapi_version}/grid"
        response = requests.get(
            url,
            auth=(cfg.admin_user, cfg.admin_pass),
            verify=cfg.verify_ssl,
            timeout=cfg.connection_timeout,
        )
        response.raise_for_status()
        print(f"OK: connected to Infoblox Grid Master at {cfg.grid_ip}.")
        return True
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"FAIL: could not connect to Infoblox: {e}")
        return False


def check_llm_connection() -> bool:
    """Verifies the configured LLM provider responds to a trivial prompt."""
    try:
        cfg = load_config()
        client = LLMClient(cfg.llm, CacheManager(cfg.cache), CircuitBreaker())
        resp = client.send_request("Reply with exactly one word: PONG")
        if "error" in resp:
            print(f"FAIL: LLM provider '{cfg.llm.provider}' returned an error: {resp['error']}")
            return False
        print(f"OK: LLM provider '{cfg.llm.provider}' responded: {resp.get('content', '').strip()[:60]}")
        return True
    except Exception as e:  # noqa: BLE001 - diagnostics should never raise
        print(f"FAIL: could not reach LLM provider: {e}")
        return False


def main(argv) -> int:
    target = argv[1] if len(argv) > 1 else "all"
    results = []
    if target in ("all", "infoblox"):
        results.append(check_infoblox_connection())
    if target in ("all", "llm"):
        results.append(check_llm_connection())
    if not results:
        print(f"Unknown target '{target}'. Use: infoblox | llm | all")
        return 2
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
