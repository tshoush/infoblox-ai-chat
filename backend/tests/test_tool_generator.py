"""Regression tests for the WAPI tool generator.

Covers the bugs fixed on 2026-06-20:
  * fetch_schema built the schema URL as ``?_schema=<obj>`` (value ignored by
    WAPI) instead of ``<obj>?_schema`` -> every per-object cache was identical.
  * _generate_header emitted an undefined ``{self.config.verify_ssl}`` set
    literal, so the generated tools.py crashed on import.
"""
import ast
from unittest.mock import MagicMock, patch

from backend.config import InfobloxConfig
from backend.tool_generator import ToolGenerator


def _config():
    return InfobloxConfig(
        grid_ip="10.0.0.1",
        admin_user="admin",
        admin_pass="pw",
        wapi_version="v2.12",
        verify_ssl=False,
    )


def _generator(tmp_path):
    gen = ToolGenerator(_config())
    gen.schema_dir = str(tmp_path / "schemas")
    return gen


def test_fetch_schema_uses_object_path_not_query_value(tmp_path):
    gen = _generator(tmp_path)
    with patch("backend.tool_generator.requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            json=lambda: {"fields": []}, raise_for_status=lambda: None
        )
        gen.fetch_schema("record:a")
    called_url = mock_get.call_args[0][0]
    assert called_url == "https://10.0.0.1/wapi/v2.12/record:a?_schema"
    assert "?_schema=" not in called_url


def test_generated_header_is_valid_python(tmp_path):
    gen = _generator(tmp_path)
    header = gen._generate_header()
    ast.parse(header)  # must not raise
    assert "VERIFY_SSL = False" in header
    assert "self." not in header  # no leaked template variable


def test_generated_crud_functions_compile(tmp_path):
    gen = _generator(tmp_path)
    code = gen._generate_crud_functions("record:a", {"supports": "rwud"})
    full = gen._generate_header() + code
    ast.parse(full)
    assert "def search_record_a(" in code
    assert "def create_record_a(" in code
    assert "def update_record_a(" in code
    assert "def delete_record_a(" in code


def test_crud_defaults_to_full_support_when_unspecified(tmp_path):
    gen = _generator(tmp_path)
    # No "supports" key -> falls back to DEFAULT_SUPPORTS (rwud).
    code = gen._generate_crud_functions("network", {})
    for verb in ("search", "create", "update", "delete"):
        assert f"def {verb}_network(" in code


def test_generate_tools_offline_writes_valid_module(tmp_path, monkeypatch):
    gen = _generator(tmp_path)
    schema_file = tmp_path / "schema.json"
    schema_file.write_text('{"supported_objects": ["record:a", "network"]}')

    out_file = tmp_path / "tools.py"
    written = {}
    real_open = open

    def fake_open(path, mode="r", *a, **k):
        if path == "backend/tools.py":
            return real_open(out_file, mode, *a, **k)
        return real_open(path, mode, *a, **k)

    monkeypatch.setattr("builtins.open", fake_open)
    # Vocabulary writes should not touch the real repo file.
    gen.vocabulary.save_vocabulary = lambda: None

    gen.generate_tools(offline_schema_path=str(schema_file))

    generated = out_file.read_text()
    ast.parse(generated)  # generated module is importable Python
    assert "def search_record_a(" in generated
    assert "def search_network(" in generated
