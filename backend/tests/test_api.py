"""Flask endpoint tests for the IACI backend.

The LLM call is patched so these run offline; they verify the HTTP wiring,
error handling, and that the app boots without an OpenAI key (RAG degrades).
"""
import pytest

from backend import app as app_module


@pytest.fixture
def client(monkeypatch):
    # Patch the live LLM so the chat endpoint is deterministic and offline.
    monkeypatch.setattr(
        app_module.ai_processor.llm_client,
        "send_request",
        lambda *a, **k: {"content": "PONG"},
    )
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_metrics(client):
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    assert "uptime_seconds" in resp.get_json()


def test_list_providers(client):
    resp = client.get("/api/providers")
    assert resp.status_code == 200
    body = resp.get_json()
    ids = {p["id"] for p in body["providers"]}
    assert {"openai", "claude", "grok", "ollama", "unsloth"} <= ids
    # Keys must never be exposed.
    assert all("api_key" not in p for p in body["providers"])


def test_set_provider_requires_provider_field(client):
    resp = client.post("/api/providers", json={})
    assert resp.status_code == 400


def test_set_provider_invokes_manager(client, monkeypatch):
    captured = {}

    def fake_set(provider, api_key=None, base_url=None, model=None, activate=True):
        captured.update(provider=provider, api_key=api_key, model=model, activate=activate)
        return {"active": provider, "providers": []}

    monkeypatch.setattr(app_module.provider_manager, "set_provider", fake_set)
    resp = client.post("/api/providers", json={"provider": "grok", "api_key": "xai-1", "model": "grok-3"})
    assert resp.status_code == 200
    assert captured["provider"] == "grok"
    assert captured["api_key"] == "xai-1"


def test_set_provider_surfaces_validation_error(client, monkeypatch):
    def fake_set(*a, **k):
        raise ValueError("OpenAI requires an API key.")

    monkeypatch.setattr(app_module.provider_manager, "set_provider", fake_set)
    resp = client.post("/api/providers", json={"provider": "openai"})
    assert resp.status_code == 400
    assert "requires an API key" in resp.get_json()["message"]


def test_status(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert "components" in body
    assert "llm_provider" in body["components"]


def test_chat_rejects_non_json_body(client):
    resp = client.post("/api/chat", data="not json", content_type="text/plain")
    assert resp.status_code == 400


def test_chat_rejects_blank_message(client):
    resp = client.post("/api/chat", json={"message": "   "})
    assert resp.status_code == 400


def test_chat_requires_message(client):
    resp = client.post("/api/chat", json={})
    assert resp.status_code == 400


def test_execute_single_operation(client, monkeypatch):
    monkeypatch.setattr(
        app_module.wapi_client, "execute_batch",
        lambda ops: [{"success": True, "status_code": 200, "data": []} for _ in ops],
    )
    resp = client.post("/api/execute", json={"operation": "network", "method": "GET", "parameters": {}})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["summary"] == {"total": 1, "succeeded": 1, "failed": 0}


def test_execute_batch_operations(client, monkeypatch):
    monkeypatch.setattr(
        app_module.wapi_client, "execute_batch",
        lambda ops: [{"success": i == 0} for i, _ in enumerate(ops)],
    )
    resp = client.post("/api/execute", json={"operations": [
        {"operation": "network", "method": "GET"},
        {"operation": "record:a", "method": "POST", "parameters": {"name": "h"}},
    ]})
    assert resp.status_code == 200
    assert resp.get_json()["summary"] == {"total": 2, "succeeded": 1, "failed": 1}


def test_openai_models_lists_iaci(client):
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.get_json()["data"]]
    assert "iaci-infoblox-wapi" in ids


def test_openai_chat_completion_nonstream(client):
    resp = client.post("/v1/chat/completions", json={
        "model": "iaci-infoblox-wapi",
        "messages": [{"role": "user", "content": "Reply with exactly: PONG"}],
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert "PONG" in body["choices"][0]["message"]["content"]


def test_openai_chat_completion_handles_list_content(client):
    # OpenAI "parts" style content must be accepted.
    resp = client.post("/v1/chat/completions", json={
        "model": "iaci-infoblox-wapi",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "Reply: PONG"}]}],
    })
    assert resp.status_code == 200
    assert "PONG" in resp.get_json()["choices"][0]["message"]["content"]


def test_openai_conversational_execute_on_confirmation(client, monkeypatch):
    """Replying 'run it' executes the plan from the prior assistant message."""
    calls = {}

    def fake_execute_batch(ops):
        calls["ops"] = ops
        return [{"success": True, "data": "network/abc"} for _ in ops]

    monkeypatch.setattr(app_module.wapi_client, "execute_batch", fake_execute_batch)
    prior_assistant = (
        "Proposed plan:\n```json\n"
        '[{"operation":"network","method":"POST","parameters":{"network":"10.9.0.0/24"}}]'
        "\n```\n👉 Reply run it to execute."
    )
    resp = client.post("/v1/chat/completions", json={
        "model": "iaci-infoblox-wapi",
        "messages": [
            {"role": "user", "content": "create network 10.9.0.0/24"},
            {"role": "assistant", "content": prior_assistant},
            {"role": "user", "content": "run it"},
        ],
    })
    assert resp.status_code == 200
    content = resp.get_json()["choices"][0]["message"]["content"]
    assert "Executed 1/1" in content
    assert calls["ops"][0]["operation"] == "network"


def test_openai_chat_completion_streaming(client):
    resp = client.post("/v1/chat/completions", json={
        "model": "iaci-infoblox-wapi",
        "stream": True,
        "messages": [{"role": "user", "content": "Reply: PONG"}],
    })
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    text = resp.get_data(as_text=True)
    assert "chat.completion.chunk" in text
    assert "data: [DONE]" in text


def test_execute_requires_operation(client):
    resp = client.post("/api/execute", json={})
    assert resp.status_code == 400


def test_execute_rejects_empty_operations_list(client):
    resp = client.post("/api/execute", json={"operations": []})
    assert resp.status_code == 400


def test_agent_executes_readonly_plan_and_synthesizes(client, monkeypatch):
    monkeypatch.setattr(app_module.ai_processor, "process_query",
                        lambda *a, **k: {"response_type": "api_call_plan", "operations": [
                            {"operation": "network", "method": "GET", "parameters": {}},
                            {"operation": "range", "method": "GET", "parameters": {}}]})
    monkeypatch.setattr(app_module.wapi_client, "execute_batch",
                        lambda ops: [{"success": True, "data": [1, 2]}, {"success": True, "data": [9]}])
    monkeypatch.setattr(app_module.ai_processor, "synthesize_answer",
                        lambda *a, **k: "You have 2 networks and 1 range.")
    resp = client.post("/api/agent", json={"message": "how many networks and ranges?"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["executed"] is True
    assert body["answer"] == "You have 2 networks and 1 range."
    assert len(body["steps"]) == 2


def test_agent_empty_plan_does_not_execute(client, monkeypatch):
    monkeypatch.setattr(app_module.ai_processor, "process_query",
                        lambda *a, **k: {"response_type": "api_call_plan", "operations": []})
    calls = {"n": 0}
    monkeypatch.setattr(app_module.wapi_client, "execute_batch",
                        lambda ops: calls.__setitem__("n", calls["n"] + 1) or [])
    resp = client.post("/api/agent", json={"message": "asdfgh"})
    assert resp.status_code == 200
    assert resp.get_json()["executed"] is False
    assert calls["n"] == 0  # never ran an empty batch


def test_api_key_auth_enforced(client, monkeypatch):
    monkeypatch.setenv("IACI_API_KEY", "s3cret")
    assert client.get("/api/health").status_code == 200          # exempt
    assert client.get("/api/status").status_code == 401          # missing key
    assert client.get("/api/status", headers={"X-API-Key": "s3cret"}).status_code == 200
    assert client.get("/api/status", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/api/status", headers={"X-API-Key": "wrong"}).status_code == 401


def test_agent_requires_approval_for_mutating_plan(client, monkeypatch):
    monkeypatch.setattr(app_module.ai_processor, "process_query",
                        lambda *a, **k: {"response_type": "api_call_proposal",
                                         "proposal": {"operation": "network", "method": "POST", "parameters": {}}})
    resp = client.post("/api/agent", json={"message": "create a network"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["executed"] is False
    assert body["requires_approval"] is True
    assert body["plan"][0]["method"] == "POST"


def test_chat_returns_response_and_session(client):
    resp = client.post("/api/chat", json={"message": "Reply with exactly: PONG"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["session_id"]
    assert body["response"] == {"response_type": "text", "content": "PONG"}
