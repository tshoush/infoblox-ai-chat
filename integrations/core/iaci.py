"""Thin HTTP client to the IACI backend, shared by every chat adapter.

The adapters (Slack/Teams/WhatsApp) hold no Grid or LLM logic — they translate
their platform's events to/from these calls.
"""
import os
from typing import Any, Dict, List

import requests


class IaciClient:
    def __init__(self, base_url: str = None, timeout: int = 90, api_key: str = None):
        self.base_url = (base_url or os.getenv("IACI_API_URL", "http://localhost:5050")).rstrip("/")
        self.timeout = timeout
        # If the backend enforces IACI_API_KEY, the bot authenticates with it.
        self.api_key = api_key or os.getenv("IACI_API_KEY")

    def _headers(self) -> Dict[str, str]:
        return {"X-API-Key": self.api_key} if self.api_key else {}

    def agent(self, message: str, session_id: str = None) -> Dict[str, Any]:
        """Reads return an answer; writes return a plan + pre-flight warnings
        with ``requires_approval`` (the backend never auto-runs a change)."""
        r = requests.post(f"{self.base_url}/api/agent",
                          json={"message": message, "session_id": session_id},
                          headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def execute(self, operations: List[Dict[str, Any]], session_id: str = None) -> Dict[str, Any]:
        r = requests.post(f"{self.base_url}/api/execute",
                          json={"operations": operations, "session_id": session_id},
                          headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def health(self) -> bool:
        try:
            return requests.get(f"{self.base_url}/api/health",
                                headers=self._headers(), timeout=5).ok
        except requests.exceptions.RequestException:
            return False
