"""Tests for the runtime WAPI client (offline, with a mocked session)."""
from unittest.mock import MagicMock

import requests

from backend.config import InfobloxConfig
from backend.wapi_client import WapiClient


def _config():
    return InfobloxConfig(grid_ip="10.0.0.1", admin_user="admin", admin_pass="pw",
                          wapi_version="v2.12", verify_ssl=False, connection_timeout=5)


def _client(objects=("record:a", "network")):
    session = MagicMock(spec=requests.Session)
    client = WapiClient(_config(), session=session, supported_objects=list(objects))
    return client, session


def _response(status=200, json_body=None, content=b"x"):
    resp = MagicMock()
    resp.ok = 200 <= status < 300
    resp.status_code = status
    resp.content = content
    resp.json.return_value = json_body if json_body is not None else {}
    resp.text = ""
    return resp


def test_get_builds_object_url_and_passes_params():
    client, session = _client()
    session.get.return_value = _response(200, [{"_ref": "record:a/x"}])
    result = client.execute("record:a", "GET", {"name": "host.example.com"})
    assert result["success"] is True
    assert result["status_code"] == 200
    url = session.get.call_args[0][0]
    assert url == "https://10.0.0.1/wapi/v2.12/record:a"
    assert session.get.call_args.kwargs["params"] == {"name": "host.example.com"}


def test_post_sends_json_body():
    client, session = _client()
    session.post.return_value = _response(201, "record:a/newref")
    result = client.execute("record:a", "POST", {"name": "h", "ipv4addr": "1.2.3.4"})
    assert result["success"] is True
    assert session.post.call_args.kwargs["json"] == {"name": "h", "ipv4addr": "1.2.3.4"}


def test_put_requires_ref_targets_reference():
    client, session = _client()
    session.put.return_value = _response(200, "record:a/x")
    result = client.execute("record:a", "PUT", {"comment": "y"}, ref="record:a/x")
    assert result["success"] is True
    assert session.put.call_args[0][0] == "https://10.0.0.1/wapi/v2.12/record:a/x"


def test_put_without_ref_is_rejected():
    client, _ = _client()
    result = client.execute("record:a", "PUT", {"comment": "y"})
    assert result["success"] is False
    assert "reference" in result["error"].lower()


def test_unknown_object_rejected():
    client, _ = _client()
    result = client.execute("not_a_real_object", "GET", {})
    assert result["success"] is False
    assert "Unknown WAPI object" in result["error"]


def test_invalid_method_rejected():
    client, _ = _client()
    result = client.execute("record:a", "PATCH", {})
    assert result["success"] is False
    assert "Unsupported method" in result["error"]


def test_http_error_surfaces_wapi_message():
    client, session = _client()
    session.get.return_value = _response(400, {"Error": "AdmConProtoError", "text": "bad field"})
    result = client.execute("record:a", "GET", {})
    assert result["success"] is False
    assert result["status_code"] == 400
    assert result["error"] == "bad field"


def test_network_exception_is_caught():
    client, session = _client()
    session.get.side_effect = requests.exceptions.ConnectionError("boom")
    result = client.execute("record:a", "GET", {})
    assert result["success"] is False
    assert "boom" in result["error"]


def test_uses_fail_fast_connect_timeout():
    """Connect timeout is capped (tuple) so an unreachable Grid fails fast."""
    cfg = _config()  # connection_timeout=5
    client = WapiClient(cfg, session=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
                        supported_objects=["network"])
    assert isinstance(client.timeout, tuple)
    connect_timeout, read_timeout = client.timeout
    assert connect_timeout <= 8
    assert read_timeout == cfg.connection_timeout


def test_preflight_flags_delete_as_destructive():
    client, _ = _client()
    warnings = client.preflight([{"operation": "network", "method": "DELETE", "ref": "network/abc"}])
    assert len(warnings) == 1
    assert warnings[0]["level"] == "danger"
    assert "DELETE" in warnings[0]["message"]


def test_preflight_flags_duplicate_create_with_details():
    client, session = _client()
    # The existence-check GET finds an existing network -> duplicate warning
    # that carries the existing object's details.
    existing = {"_ref": "network/existing", "network": "10.0.0.0/24", "comment": "prod"}
    session.get.return_value = _response(200, [existing])
    warnings = client.preflight([
        {"operation": "network", "method": "POST", "parameters": {"network": "10.0.0.0/24"}}])
    assert len(warnings) == 1
    assert "already exists" in warnings[0]["message"]
    assert warnings[0]["details"]["comment"] == "prod"
    # The existence check should request useful detail fields.
    assert "_return_fields" in session.get.call_args.kwargs["params"]


def test_preflight_no_warning_when_create_is_new():
    client, session = _client()
    session.get.return_value = _response(200, [])  # nothing existing
    warnings = client.preflight([
        {"operation": "network", "method": "POST", "parameters": {"network": "10.0.0.0/24"}}])
    assert warnings == []


def test_execute_batch_chains_ref_from_get_to_delete():
    """A GET that locates an object feeds its _ref to a following DELETE."""
    client, session = _client()
    session.get.return_value = _response(200, [{"_ref": "network/REAL123:10.0.0.0/24/default"}])
    session.delete.return_value = _response(200, {"success": True})
    results = client.execute_batch([
        {"operation": "network", "method": "GET", "parameters": {"network": "10.0.0.0/24"}},
        {"operation": "network", "method": "DELETE", "ref": "<network_ref_from_previous_GET>"},
    ])
    assert all(r["success"] for r in results)
    # DELETE must have targeted the real _ref resolved from the GET.
    delete_url = session.delete.call_args[0][0]
    assert delete_url.endswith("network/REAL123:10.0.0.0/24/default")


def test_execute_batch_refuses_ref_chain_on_type_mismatch():
    """A GET on 'network' must NOT feed a DELETE on 'record:a' (wrong object)."""
    client, session = _client()
    session.get.return_value = _response(200, [{"_ref": "network/REAL:10.0.0.0/24/default"}])
    results = client.execute_batch([
        {"operation": "network", "method": "GET", "parameters": {}},
        {"operation": "record:a", "method": "DELETE", "ref": "<ref_from_previous_GET>"},
    ])
    assert results[0]["success"] is True
    assert results[1]["success"] is False
    assert "no matching object reference" in results[1]["error"].lower()
    session.delete.assert_not_called()


def test_is_placeholder_ref():
    assert WapiClient._is_placeholder_ref("<ref_from_previous_GET>")
    assert WapiClient._is_placeholder_ref(None)
    assert WapiClient._is_placeholder_ref("")
    assert not WapiClient._is_placeholder_ref("network/REAL123:10.0.0.0/24/default")


def test_execute_batch_collects_all_results():
    client, session = _client()
    session.get.return_value = _response(200, [])
    session.post.return_value = _response(201, "ref")
    results = client.execute_batch([
        {"operation": "network", "method": "GET", "parameters": {}},
        {"operation": "record:a", "method": "POST", "parameters": {"name": "h"}},
        "not-a-dict",
    ])
    assert len(results) == 3
    assert results[0]["success"] is True
    assert results[1]["success"] is True
    assert results[2]["success"] is False
