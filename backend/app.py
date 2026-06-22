from flask import Flask, jsonify, request
from flask_cors import CORS
from backend.config import load_config
from backend.cache import CacheManager
from backend.circuit_breaker import CircuitBreaker
from backend.rag_system import RAGSystem
from backend.vocabulary import Vocabulary
from backend.llm_client import LLMClient
from backend.ai_processor import AIProcessor
from backend.wapi_client import WapiClient
from backend.openai_compat import create_openai_blueprint
from backend.provider_manager import ProviderManager
import time
import logging
import threading
import hmac
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
config = load_config()

# Enable CORS. Defaults to "*" for local dev; set IACI_CORS_ORIGINS to a
# comma-separated allowlist (e.g. your UI origin) to lock it down in production.
_cors = os.getenv("IACI_CORS_ORIGINS", "*")
_origins = "*" if _cors.strip() == "*" else [o.strip() for o in _cors.split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": _origins}, r"/v1/*": {"origins": _origins}})

# Optional API-key auth. If IACI_API_KEY is set, every /api/* and /v1/* request
# must present it (X-API-Key header, or "Authorization: Bearer <key>"). Disabled
# (open) when unset, to keep local dev/tests frictionless. /api/health is exempt
# so health checks/probes keep working.
_PUBLIC_PATHS = {"/api/health"}


@app.before_request
def require_api_key():
    if request.method == "OPTIONS":
        return  # let CORS preflight through
    api_key = os.getenv("IACI_API_KEY")
    if not api_key:
        return  # auth disabled
    path = request.path
    if path in _PUBLIC_PATHS or not (path.startswith("/api/") or path.startswith("/v1/")):
        return
    provided = request.headers.get("X-API-Key")
    if not provided:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            provided = auth[7:]
    if not provided or not hmac.compare_digest(provided, api_key):
        return jsonify({"error": "Unauthorized"}), 401

# Initialize the cache manager
cache_manager = CacheManager(config.cache)

# Initialize the circuit breaker
circuit_breaker = CircuitBreaker()

# Initialize the RAG system
rag_system = RAGSystem()

# Initialize the vocabulary
vocabulary = Vocabulary()

# Initialize LLM Client and AI Processor
llm_client = LLMClient(config.llm, cache_manager, circuit_breaker)
ai_processor = AIProcessor(llm_client, rag_system, vocabulary)

# Manages the active LLM provider + per-provider API keys (runtime-switchable).
provider_manager = ProviderManager(llm_client)

# Initialize the WAPI client used to execute approved operations.
wapi_client = WapiClient(config.infoblox)

# Dedicated audit logger for executed operations.
audit_logger = logging.getLogger("iaci.audit")

# OpenAI-compatible endpoints (/v1/*) so any OpenAI-compatible chat UI
# (Open WebUI, LibreChat, ...) can use IACI as a selectable model. IACI is
# advertised as several models — the default plus iaci-<provider> for each
# configured provider — so the UI's model dropdown switches the agent's LLM.
from backend import providers as _providers


def _resolve_processor(model):
    """Map a requested model id to the AIProcessor for that provider."""
    provider = None
    if isinstance(model, str) and model.startswith("iaci-") and model != "iaci-infoblox-wapi":
        provider = _providers.canonical(model[len("iaci-"):])
    if not provider or provider == provider_manager.active:
        return ai_processor
    client = provider_manager.client_for(provider)
    if client is None:
        return ai_processor  # not configured -> fall back to the active provider
    return AIProcessor(client, rag_system, vocabulary)


app.register_blueprint(create_openai_blueprint(
    ai_processor, wapi_client,
    list_model_ids=provider_manager.model_ids,
    resolve_processor=_resolve_processor,
))

# Basic metrics (request_count is mutated from multiple worker threads)
request_count = 0
request_count_lock = threading.Lock()
start_time = time.time()

class APIError(Exception):
    def __init__(self, message, status_code=500, payload=None):
        super().__init__()
        self.message = message
        self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv

@app.errorhandler(APIError)
def handle_api_error(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response

@app.before_request
def log_request():
    global request_count
    with request_count_lock:
        request_count += 1
    app.logger.info(f"Request received: {request.method} {request.path}")

@app.after_request
def log_response(response):
    app.logger.info(f"Response sent: {request.method} {request.path} - Status {response.status_code}")
    return response

@app.route("/api/health")
def health_check():
    """Health check endpoint to verify that the server is running."""
    return jsonify({"status": "ok"})

@app.route("/api/providers", methods=["GET"])
def list_providers():
    """Lists supported LLM providers with examples and which keys are set."""
    return jsonify(provider_manager.public())

@app.route("/api/providers", methods=["POST"])
def set_provider():
    """Saves a provider's API key/base_url/model and (by default) activates it."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError("Request body must be a JSON object", 400)
    provider = payload.get("provider")
    if not provider:
        raise APIError("'provider' is required", 400)
    try:
        result = provider_manager.set_provider(
            provider,
            api_key=payload.get("api_key"),
            base_url=payload.get("base_url"),
            model=payload.get("model"),
            activate=payload.get("activate", True),
        )
    except ValueError as e:
        raise APIError(str(e), 400)
    return jsonify(result)

@app.route("/api/providers/models", methods=["POST"])
def provider_models():
    """Fetches a provider's live model list once an API key is supplied."""
    payload = request.get_json(silent=True) or {}
    provider = payload.get("provider")
    if not provider:
        raise APIError("'provider' is required", 400)
    try:
        result = provider_manager.list_models(
            provider, api_key=payload.get("api_key"), base_url=payload.get("base_url"))
    except ValueError as e:
        raise APIError(str(e), 400)
    return jsonify(result)

@app.route("/api/providers/test", methods=["POST"])
def test_provider():
    """Sends a tiny prompt through the active provider to verify it works."""
    return jsonify(provider_manager.test())

@app.route("/api/status")
def status():
    """Reports the readiness of each downstream component."""
    return jsonify({
        "status": "ok",
        "components": {
            "llm_provider": llm_client.config.provider,
            "llm_model": llm_client.config.model or llm_client._default_model(),
            "cache": "connected" if cache_manager.redis_client else "disabled",
            "rag": "enabled" if getattr(rag_system, "vector_store", None) else "disabled",
            "circuit_breaker": circuit_breaker.state,
        },
        "uptime_seconds": round(time.time() - start_time, 2),
    })

@app.route("/api/metrics")
def metrics():
    """Provides basic application metrics."""
    uptime = time.time() - start_time
    return jsonify({
        "request_count": request_count,
        "uptime_seconds": round(uptime, 2)
    })

@app.route("/api/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError("Request body must be a JSON object", 400)

    user_message = payload.get("message")
    session_id = payload.get("session_id")

    if not user_message or not isinstance(user_message, str) or not user_message.strip():
        raise APIError("Message is required", 400)

    if not session_id:
        session_id = cache_manager.generate_session_id()

    # Retrieve session context (e.g., previous messages, user preferences)
    session_context = cache_manager.get_session_data(session_id)

    # Process the user's message using the AI processor
    response = ai_processor.process_query(user_message, session_context.get("context"))

    # Update session context (e.g., add current message and response)
    # For simplicity, just storing the last message and response as context
    new_session_context = {"last_message": user_message, "last_response": response, "context": response.get("content")}
    cache_manager.set_session_data(session_id, new_session_context)

    return jsonify({"session_id": session_id, "response": response})

@app.route("/api/execute", methods=["POST"])
def execute():
    """Executes one or more user-approved WAPI operations.

    Accepts either a single operation object or ``{"operations": [...]}`` for
    batch execution. Every operation is validated and audit-logged.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError("Request body must be a JSON object", 400)

    if "operations" in payload:
        operations = payload.get("operations")
        if not isinstance(operations, list) or not operations:
            raise APIError("'operations' must be a non-empty list", 400)
    else:
        if not payload.get("operation"):
            raise APIError("'operation' is required", 400)
        operations = [payload]

    session_id = payload.get("session_id")
    for op in operations:
        audit_logger.info(
            "EXECUTE session=%s method=%s operation=%s ref=%s",
            session_id, (op.get("method") if isinstance(op, dict) else None),
            (op.get("operation") if isinstance(op, dict) else None),
            (op.get("ref") if isinstance(op, dict) else None),
        )

    results = wapi_client.execute_batch(operations)
    succeeded = sum(1 for r in results if r.get("success"))
    audit_logger.info("EXECUTE session=%s completed %d/%d succeeded", session_id, succeeded, len(results))

    return jsonify({
        "session_id": session_id,
        "results": results,
        "summary": {"total": len(results), "succeeded": succeeded, "failed": len(results) - succeeded},
    })

@app.route("/api/agent", methods=["POST"])
def agent():
    """Answers a question by planning WAPI calls, running the read-only ones,
    and synthesizing the results into a plain-English answer.

    Read-only plans (all GET) run automatically. Any plan that would modify the
    Grid is returned for explicit approval instead of being executed here.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError("Request body must be a JSON object", 400)

    message = payload.get("message")
    if not message or not isinstance(message, str) or not message.strip():
        raise APIError("Message is required", 400)

    plan = ai_processor.process_query(message)
    rtype = plan.get("response_type")

    if rtype == "text":
        return jsonify({"answer": plan.get("content"), "executed": False, "steps": []})

    operations = plan.get("operations") or [plan.get("proposal")]
    operations = [op for op in operations if isinstance(op, dict)]

    if not operations:
        # No concrete calls — don't run an empty batch and synthesize a
        # hallucinated answer; ask the user to rephrase.
        return jsonify({"answer": "I couldn't turn that into a specific Infoblox operation. "
                                  "Could you rephrase or be more specific?",
                        "executed": False, "steps": []})

    if any((op.get("method") or "GET").upper() != "GET" for op in operations):
        # Don't silently mutate the Grid — hand the plan back for approval,
        # with pre-flight warnings (duplicates/destructive) for the approver.
        return jsonify({
            "answer": None,
            "executed": False,
            "requires_approval": True,
            "plan": operations,
            "warnings": wapi_client.preflight(operations),
            "message": "This plan would modify the Grid. Review and run it explicitly.",
        })

    results = wapi_client.execute_batch(operations)
    answer = ai_processor.synthesize_answer(message, operations, results)
    return jsonify({
        "answer": answer,
        "executed": True,
        "steps": [{"call": op, "result": res} for op, res in zip(operations, results)],
    })

@app.errorhandler(404)
def not_found(error):
    app.logger.error(f"404 Not Found: {request.path}")
    return jsonify({"error": "Not Found", "code": 404}), 404

@app.errorhandler(500)
def internal_server_error(error):
    app.logger.exception(f"500 Internal Server Error: {error}")
    return jsonify({"error": "Internal Server Error", "code": 500}), 500

if __name__ == "__main__":
    # Debug mode exposes the Werkzeug debugger (arbitrary code execution); only
    # enable it explicitly via FLASK_DEBUG. Production should run under gunicorn.
    import os
    debug = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true", "t")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=debug)