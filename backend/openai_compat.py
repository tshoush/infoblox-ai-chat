"""OpenAI-compatible API surface for IACI.

Exposes ``/v1/models`` and ``/v1/chat/completions`` (streaming + non-streaming)
so any OpenAI-compatible chat client (Open WebUI, LibreChat, etc.) can point at
the IACI backend as a selectable model. Each request is run through the same
``AIProcessor`` pipeline as ``/api/chat``; WAPI-call proposals are rendered as a
readable assistant message with the JSON the user can run via ``/api/execute``.
"""
import json
import re
import time
import uuid

from flask import Blueprint, request, jsonify, Response

DEFAULT_MODEL_ID = "iaci-infoblox-wapi"

# A bare affirmation that should run the previously-proposed plan. Matches the
# WHOLE message so it can't fire on a normal request that merely starts with "yes".
_AFFIRM_RE = re.compile(
    r"^\s*(yes|y|yep|yeah|run(\s+(it|them|the\s+plan|all))?|execute(\s+(it|them))?|"
    r"do\s+it|go(\s+ahead)?|proceed|confirm|apply(\s+it)?|ok(ay)?|sounds\s+good)\s*[.!]*\s*$",
    re.IGNORECASE,
)


def _message_text(msg):
    content = msg.get("content", "")
    if isinstance(content, list):
        return " ".join(
            p.get("text", "") for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ).strip()
    return (content or "").strip()


def _ops_from_text(text):
    """Reconstructs a list of WAPI call objects from fenced ```json blocks in
    a prior assistant message (proposal object, operations object, or array)."""
    for block in reversed(re.findall(r"```(?:json)?\s*(.*?)```", text or "", re.DOTALL | re.IGNORECASE)):
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("operations"), list):
            ops = [o for o in data["operations"] if isinstance(o, dict) and "operation" in o]
            if ops:
                return ops
        if isinstance(data, list):
            ops = [o for o in data if isinstance(o, dict) and "operation" in o]
            if ops:
                return ops
        if isinstance(data, dict) and "operation" in data and "method" in data:
            return [data]
    return None


def _find_pending_operations(messages):
    """Scans backward for the most recent assistant message proposing call(s)."""
    for msg in reversed(messages or []):
        if msg.get("role") == "assistant":
            ops = _ops_from_text(_message_text(msg))
            if ops:
                return ops
    return None


def _render_execution_results(operations, results):
    lines = []
    succeeded = 0
    for op, res in zip(operations, results):
        ok = bool(res.get("success"))
        succeeded += ok
        tag = "✅" if ok else "❌"
        detail = json.dumps(res.get("data")) if ok else (res.get("error") or "failed")
        if len(detail) > 200:
            detail = detail[:200] + " …"
        lines.append(f"{tag} `{op.get('method')} {op.get('operation')}` — {detail}")
    header = f"**Executed {succeeded}/{len(operations)} call(s):**"
    return header + "\n\n" + "\n".join(lines)


def _extract_last_user_message(messages):
    """Returns the text of the last user message (handles list-style content)."""
    for msg in reversed(messages or []):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            # OpenAI "parts" form: [{"type":"text","text":"..."}, ...]
            return " ".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ).strip()
        return (content or "").strip()
    return ""


def _render_plan_for_approval(operations, wapi_client):
    """Renders a write plan with pre-flight warnings (duplicates/destructive)."""
    single = len(operations) == 1
    header = ("**Proposed Infoblox WAPI call:**" if single
              else f"**Proposed plan — {len(operations)} WAPI calls (run in order):**")
    lines = [header, ""]
    for i, op in enumerate(operations, 1):
        lines.append(f"{i}. `{op.get('method')} {op.get('operation')}`")

    body = operations[0] if single else operations
    block = "\n\n```json\n" + json.dumps(body, indent=2) + "\n```\n"

    warn_txt = ""
    warnings = wapi_client.preflight(operations) if wapi_client is not None else []
    if warnings:
        wl = ["", "⚠️ **Heads up:**"]
        detail_blocks = []
        for w in warnings:
            icon = "🛑" if w.get("level") == "danger" else "⚠️"
            wl.append(f"- {icon} Step {w['index'] + 1}: {w['message']}")
            details = w.get("details")
            if details:
                obj = operations[w["index"]].get("operation")
                detail_blocks.append(
                    f"**Existing {obj} (step {w['index'] + 1}):**\n"
                    "```json\n" + json.dumps(details, indent=2) + "\n```"
                )
        warn_txt = "\n".join(wl) + "\n"
        if detail_blocks:
            warn_txt += "\n" + "\n\n".join(detail_blocks) + "\n"

    return "\n".join(lines) + block + warn_txt + "\n👉 Reply **run it** to execute, or tell me what to change."


def _assistant_content(ai_processor, wapi_client, query, pending):
    """Produces the assistant message: answers reads, gates writes, revises plans.

    If `pending` (a previously-proposed plan) is set and the user's reply isn't a
    bare confirmation, the reply is treated as an amendment/new request and the
    plan is re-planned accordingly.
    """
    if pending:
        revised = ai_processor.revise_plan(pending, query)
        if revised is not None:
            result = {"response_type": "api_call_plan", "operations": revised}
        else:
            result = ai_processor.process_query(query)
    else:
        result = ai_processor.process_query(query)

    rtype = result.get("response_type")
    if rtype == "text":
        return result.get("content", "") or "(no response)"

    ops = result.get("operations") or [result.get("proposal", {})]
    ops = [o for o in ops if isinstance(o, dict)]
    if not ops:
        return result.get("content", "") or "(no response)"

    # Read-only -> execute now and answer from the combined results.
    if wapi_client is not None and all((o.get("method") or "GET").upper() == "GET" for o in ops):
        results = wapi_client.execute_batch(ops)
        answer = ai_processor.synthesize_answer(query, ops, results)
        ran = ", ".join(f"{o.get('method')} {o.get('operation')}" for o in ops)
        return f"{answer}\n\n_(ran {len(ops)} read call(s): {ran})_"

    # Writes -> show the plan + warnings and wait for "run it".
    return _render_plan_for_approval(ops, wapi_client)


def create_openai_blueprint(ai_processor, wapi_client=None,
                            model_id: str = DEFAULT_MODEL_ID,
                            list_model_ids=None, resolve_processor=None) -> Blueprint:
    """Build the /v1 blueprint.

    list_model_ids(): optional callable -> list of advertised model ids (e.g.
        ["iaci-infoblox-wapi", "iaci-openai", "iaci-claude"]). Defaults to one id.
    resolve_processor(model): optional callable -> the AIProcessor to use for a
        given requested model (so each iaci-<provider> routes to that provider).
    """
    bp = Blueprint("openai_compat", __name__)

    def _model_ids():
        return list_model_ids() if list_model_ids else [model_id]

    def _processor_for(model):
        return resolve_processor(model) if resolve_processor else ai_processor

    @bp.route("/v1/models", methods=["GET"])
    def list_models():
        return jsonify({
            "object": "list",
            "data": [
                {"id": mid, "object": "model", "created": 0, "owned_by": "iaci"}
                for mid in _model_ids()
            ],
        })

    @bp.route("/v1/chat/completions", methods=["POST"])
    def chat_completions():
        body = request.get_json(silent=True) or {}
        model = body.get("model") or model_id
        stream = bool(body.get("stream", False))
        messages = body.get("messages", [])
        query = _extract_last_user_message(messages)
        # Route to the provider implied by the requested model (iaci-<provider>).
        processor = _processor_for(model)

        # Conversational execution: if the user just confirmed ("run it") and the
        # previous assistant turn proposed call(s), execute them now. This is how
        # writes get run from a generic chat UI that has no Run button.
        pending = _find_pending_operations(messages) if wapi_client is not None else None
        is_confirm = bool(query and _AFFIRM_RE.match(query))

        if pending and is_confirm:
            results = wapi_client.execute_batch(pending)
            content = _render_execution_results(pending, results)
        elif query:
            # A non-bare-confirmation reply to a pending plan is an amendment;
            # pass the pending plan so it can be revised instead of re-planned cold.
            content = _assistant_content(processor, wapi_client, query,
                                         pending if not is_confirm else None)
        else:
            content = "Ask me to create, search, update or delete an Infoblox WAPI object."

        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())

        if not stream:
            return jsonify({
                "id": completion_id,
                "object": "chat.completion",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })

        def event_stream():
            base = {"id": completion_id, "object": "chat.completion.chunk",
                    "created": created, "model": model}
            # role delta
            yield "data: " + json.dumps({**base, "choices": [
                {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}) + "\n\n"
            # content delta (single chunk is valid SSE for OpenAI clients)
            yield "data: " + json.dumps({**base, "choices": [
                {"index": 0, "delta": {"content": content}, "finish_reason": None}]}) + "\n\n"
            # stop
            yield "data: " + json.dumps({**base, "choices": [
                {"index": 0, "delta": {}, "finish_reason": "stop"}]}) + "\n\n"
            yield "data: [DONE]\n\n"

        return Response(event_stream(), mimetype="text/event-stream")

    return bp
