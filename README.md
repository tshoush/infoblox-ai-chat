# Infoblox AI Chat Interface (IACI)

An intelligent chat interface that bridges natural language interaction with Infoblox NIOS Web API (WAPI) operations. The system enables network administrators to manage their Infoblox infrastructure using conversational AI, eliminating the need to learn complex API syntax.

## Features

- **Natural Language Processing**: Convert plain English queries into precise WAPI operations
- **Dynamic Tool Generation**: Automatically discover and generate tools for all supported WAPI objects
- **User Approval Workflow**: Review and edit proposed API calls before execution for safety and accuracy
- **RAG-Enhanced Documentation**: Leverage comprehensive Infoblox documentation for intelligent responses
- **Multi-LLM Support**: Compatible with OpenAI, Claude (Anthropic), and Ollama (local) providers
- **Marriott-Inspired UI**: Professional, accessible interface with responsive design

## Architecture

- **Backend**: Python Flask with dynamic WAPI tool generation
- **Frontend**: React with Marriott-inspired design system
- **AI Processing**: Multi-provider LLM integration with RAG system
- **Documentation**: Comprehensive requirements, design, and implementation specifications

## Project Structure

```
.kiro/specs/infoblox-ai-chat/
├── requirements.md    # Detailed requirements with EARS format
├── design.md         # Comprehensive system design
└── tasks.md          # Implementation plan with 7 phases
```

## Getting Started

### Quick start (recommended)

One script sets up the backend and lets you pick a single chat UI — you do **not**
need all of them:

```bash
./setup.sh            # interactive menu of interfaces (UIs + team chatbots)
./setup.sh react      # built-in React UI (or: openwebui | librechat | none)
./setup.sh slack      # team Slack bot       (integrations/slack/README.md)
./setup.sh teams      # Microsoft Teams bot  (integrations/teams/README.md)
./setup.sh whatsapp   # WhatsApp bot         (integrations/whatsapp/README.md)
./setup.sh stop       # stop everything it started
```

Team chatbots (Slack/Teams/WhatsApp) share one adapter core (`integrations/core/`):
reads are open to the channel, **changes require approval** (button click) by a
user in `*_WRITER_USERS`, deletes need `*_ADMIN_USERS`, the approver is
re-checked, approvals are single-use (idempotent), and pre-flight duplicate/
destructive warnings show before running.

The backend always runs; you choose exactly one UI:
- **IACI React UI** — no extra installs (Node only), has the provider/model picker, Run buttons, and warnings. **Recommended.**
- **Open WebUI** / **LibreChat** — optional off-the-shelf chat apps (Docker); the script wires them to the backend's OpenAI-compatible `/v1` endpoint and verifies they can reach it.

First run creates `.env` from `.env.example` if missing — fill in your Grid IP/creds and LLM key, then re-run.

### Manual setup

### Backend

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env            # then fill in your Grid + LLM credentials
python -m pytest backend/tests  # run the offline test suite
python backend/app.py           # dev server on :5000 (set FLASK_DEBUG=1 to debug)
```

For production, run under gunicorn (used by the Dockerfile):

```bash
gunicorn --bind 0.0.0.0:5000 --workers 4 backend.app:app
```

Regenerate the WAPI tool stubs from the Grid schema:

```bash
python run_tool_generator.py            # live, fetches schemas from the Grid
python run_tool_generator.py --offline  # offline, uses local schema.json
```

### Older Linux (RHEL 7 / old glibc)

The backend runs on Python 3.8+ (tested on RHEL 7.9 with Python 3.11). Two RAG
deps don't build there and aren't required — RAG **degrades gracefully** without
them (the rest of the system, including live Grid execution, works fully):

```bash
python3.11 -m venv .venv
.venv/bin/pip install --prefer-binary -r backend/requirements.txt   # skip faiss-cpu if it fails
# RAG vector search needs faiss-cpu; if it won't build, leave it out — IACI logs
# "RAG disabled" and continues. Add it later via conda or a prebuilt wheel.
```

### RAG documentation index

The assistant grounds answers in Infoblox docs via a FAISS index built from
files in `rag_docs/` (PDF, HTML, YAML). Embeddings require `OPENAI_API_KEY`.
The index is built **offline** and persisted to `rag_index/` so the app only
loads it at boot (it never re-embeds on startup).

```bash
# Add docs to rag_docs/ (e.g. the Infoblox NIOS WAPI Reference Guide PDF), then:
python scripts/build_rag_index.py --dry-run   # count chunks + estimate cost
python scripts/build_rag_index.py             # build + persist rag_index/

# Optional: pull the per-object WAPI HTML reference into rag_docs/wapidoc/
bash scripts/fetch_wapidoc.sh                 # then rebuild the index
```

`rag_docs/*.pdf`, `rag_docs/wapidoc/`, and `rag_index/` are git-ignored
(large/derived artifacts). Currently indexed: the NIOS WAPI 9.x Reference Guide,
the NIOS 9.0.x docs, the per-object WAPI 2.13.7 HTML reference, and a generated
schema summary.

### Open-source chat UIs (OpenAI-compatible)

The backend exposes an OpenAI-compatible surface (`GET /v1/models`,
`POST /v1/chat/completions`, streaming + non-streaming), so any OpenAI-compatible
chat app can use IACI as a selectable model. Two are pre-wired:

```bash
# Backend must be running on :5050 first (see below).

# Open WebUI -> http://localhost:3001  (no login; model preselected)
docker run -d -p 3001:8080 --add-host=host.docker.internal:host-gateway \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:5050/v1 \
  -e OPENAI_API_KEY=iaci -e WEBUI_AUTH=false \
  --name iaci-openwebui ghcr.io/open-webui/open-webui:main

# LibreChat -> http://localhost:3002  (register a local account, pick the "IACI" endpoint)
cd librechat && docker compose up -d
```

Both UIs also let end users add their *own* provider connections (OpenAI key,
Ollama, etc.) in their settings — selecting the `iaci-infoblox-wapi` model routes
through the Infoblox WAPI agent; other connections are plain chat.

### Frontend (custom React UI)

```bash
cd frontend && npm install && npm start   # talks to REACT_APP_API_URL (default http://localhost:5000)
```

### Docker

```bash
docker compose up --build   # backend :5000, redis, mock Infoblox WAPI :8080
```

### HTTP API

| Method | Path           | Purpose                                              |
|--------|----------------|------------------------------------------------------|
| GET    | `/api/health`  | Liveness probe                                       |
| GET    | `/api/status`  | Component readiness (LLM, cache, RAG, circuit breaker)|
| GET    | `/api/metrics` | Request count and uptime                             |
| POST   | `/api/chat`    | Natural-language → WAPI call proposal or multi-step plan |
| POST   | `/api/execute` | Execute approved WAPI operation(s) (single or batch) |
| POST   | `/api/agent`   | Plan → auto-run read-only calls → synthesize an answer (writes need approval) |
| GET/POST | `/v1/*`      | OpenAI-compatible surface for Open WebUI / LibreChat  |

`/api/chat` may return a single `api_call_proposal` or an ordered
`api_call_plan` (`{"operations": [...]}`) when a request needs several
coordinated calls (e.g. create a network **and** its DHCP range + options).
`/api/execute` runs a plan as a batch in order. `/api/agent` additionally
executes read-only plans and answers the question from the combined results.

See `.kiro/specs/infoblox-ai-chat/` for the full requirements, design, and task plan.

## Target Users

- Network administrators managing Infoblox NIOS systems
- DevOps engineers automating network infrastructure
- IT professionals seeking simplified WAPI interaction

## Technology Stack

- **Backend**: Flask 3.0.3, Python 3.12
- **Frontend**: React 18.3.1 with react-autosuggest
- **AI**: Multi-provider LLM support (OpenAI, Claude, Ollama)
- **Documentation**: RAG system with PDF, YAML, and HTML sources
- **Deployment**: Docker with production optimization

## Development Phases

1. **Foundation**: Project structure and core infrastructure
2. **Backend Services**: API, RAG system, and AI processing
3. **AI Integration**: LLM processing and intent recognition
4. **Frontend UI**: React components with Marriott design
5. **Advanced Features**: Performance optimization and accessibility
6. **Testing**: Comprehensive test suite with CI/CD
7. **Production**: Deployment, monitoring, and documentation

## License

This project is part of a specification-driven development approach for enterprise network management automation.