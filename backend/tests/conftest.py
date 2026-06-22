"""Shared pytest setup for the IACI backend test suite.

Ensures the repo root is importable so the ``backend.*`` package imports used
throughout the code resolve regardless of where pytest is invoked from.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: tests that make real network calls to the LLM provider"
    )
