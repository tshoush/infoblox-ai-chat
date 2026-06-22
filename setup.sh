#!/usr/bin/env bash
#
# IACI setup & launcher.
#
# Sets up the backend (always required) and lets you pick ONE chat UI:
#   - IACI's built-in React UI  (no extra installs — recommended)
#   - Open WebUI                (Docker)
#   - LibreChat                 (Docker + MongoDB)
#   - Backend only              (use the API or your own OpenAI-compatible client)
#
# Usage:
#   ./setup.sh                 # interactive menu
#   ./setup.sh react           # built-in UI
#   ./setup.sh openwebui       # Open WebUI
#   ./setup.sh librechat       # LibreChat
#   ./setup.sh none            # backend only
#   ./setup.sh stop            # stop everything this script started
#
# On first run it asks which Python to build the venv with (default = auto-
# detected). Set IACI_PYTHON=/path/to/python to skip the prompt (CI/non-TTY).
#
# For Open WebUI / LibreChat it uses Docker or native podman, asking which if
# both are present. Set IACI_RUNTIME=docker|podman to choose non-interactively
# (podman is auto-selected on hosts with no Docker, e.g. RHEL/CentOS).
#
# Ports (override via env): IACI_BACKEND_PORT=5050 IACI_REACT_PORT=3300
#                           IACI_OPENWEBUI_PORT=3001 IACI_LIBRECHAT_PORT=3002
set -euo pipefail
cd "$(dirname "$0")"

BACKEND_PORT="${IACI_BACKEND_PORT:-5050}"
REACT_PORT="${IACI_REACT_PORT:-3300}"
OPENWEBUI_PORT="${IACI_OPENWEBUI_PORT:-3001}"
LIBRECHAT_PORT="${IACI_LIBRECHAT_PORT:-3002}"
VENV="./.venv"
PY="$VENV/bin/python"
LOGDIR="/tmp/iaci-logs"; mkdir -p "$LOGDIR"

log()  { printf "\033[36m[iaci]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[iaci]\033[0m %s\n" "$*"; }
err()  { printf "\033[31m[iaci] ERROR:\033[0m %s\n" "$*" >&2; }

require() { command -v "$1" >/dev/null 2>&1 || { err "'$1' is required but not installed."; exit 1; }; }

# Is "$1" a runnable Python >= 3.8? (works for names on PATH or absolute paths)
_valid_py() {
  command -v "$1" >/dev/null 2>&1 && \
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,8) else 1)' 2>/dev/null
}

# Auto-detect the newest Python >= 3.8 on PATH (echoes its full path, or nothing).
detect_python() {
  for p in python3.12 python3.11 python3.10 python3.9 python3.8 python3 python; do
    if _valid_py "$p"; then command -v "$p"; return 0; fi
  done
  return 1
}

# Resolve which Python to build the venv with. Order:
#   1. IACI_PYTHON env var (non-interactive override),
#   2. interactive prompt (default = auto-detected), accepting a full path,
#   3. the auto-detected default when there's no TTY (ssh/CI).
# Prompts/warnings go to stderr so only the chosen path lands on stdout.
choose_python() {
  if [ -n "${IACI_PYTHON:-}" ]; then
    _valid_py "$IACI_PYTHON" || { err "IACI_PYTHON='$IACI_PYTHON' is not a usable Python 3.8+ interpreter."; exit 1; }
    echo "$IACI_PYTHON"; return 0
  fi
  default="$(detect_python || true)"
  if [ -t 0 ]; then
    while true; do
      printf "\033[36m[iaci]\033[0m Python interpreter to use [%s]: " "${default:-/full/path/to/python3}" >&2
      read -r ans
      pybin="${ans:-$default}"
      [ -n "$pybin" ] || { printf "  please enter a path or name\n" >&2; continue; }
      if _valid_py "$pybin"; then echo "$pybin"; return 0; fi
      printf "  '%s' isn't a usable Python 3.8+ — try again (a full path like /opt/python3.11/bin/python3 is fine)\n" "$pybin" >&2
    done
  fi
  [ -n "$default" ] || { err "No Python 3.8+ found and no terminal to prompt. Set IACI_PYTHON=/path/to/python and re-run."; exit 1; }
  echo "$default"
}

# Is something listening on a TCP port? Works without lsof (RHEL minimal images).
port_busy() {
  if command -v lsof >/dev/null 2>&1; then lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; return; fi
  if command -v ss   >/dev/null 2>&1; then ss -ltn 2>/dev/null | grep -q ":$1 "; return; fi
  python3 - "$1" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket(); s.settimeout(0.3)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}

# --- backend ---------------------------------------------------------------
setup_backend() {
  if [ ! -x "$PY" ]; then
    pybin="$(choose_python)"
    log "Creating virtualenv (.venv) with $pybin ($("$pybin" --version 2>&1))…"
    "$pybin" -m venv "$VENV"
  fi
  log "Installing backend dependencies (prefer prebuilt wheels)…"
  "$PY" -m pip install -q --upgrade pip wheel
  "$PY" -m pip install -q --prefer-binary -r backend/requirements.txt
  # Optional RAG vector store (faiss). Best-effort: it has no wheel on some
  # platforms (e.g. RHEL 7 / old glibc) — if it won't install, RAG degrades
  # gracefully and the rest of IACI still works.
  if [ -f backend/requirements-rag.txt ]; then
    if "$PY" -m pip install -q --prefer-binary -r backend/requirements-rag.txt 2>/dev/null; then
      log "RAG vector store (faiss) installed."
    else
      warn "Could not install the optional RAG vector store (faiss) on this platform — RAG will be disabled. Core IACI is unaffected."
    fi
  fi
  if [ ! -f .env ]; then
    cp .env.example .env
    warn ".env created from .env.example — edit it with your Grid IP/creds and LLM key, then re-run."
    exit 0
  fi
}

start_backend() {
  if port_busy "$BACKEND_PORT"; then
    if curl -fsS "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
      log "Backend already running on :$BACKEND_PORT."
      return 0
    fi
    err "Port $BACKEND_PORT is busy but not the IACI backend. Set IACI_BACKEND_PORT to a free port."
    exit 1
  fi
  log "Starting backend on :$BACKEND_PORT…"
  FLASK_DEBUG=0 PORT="$BACKEND_PORT" nohup "$PY" -m backend.app >"$LOGDIR/backend.log" 2>&1 &
  for _ in $(seq 1 30); do
    curl -fsS "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1 && { log "Backend healthy."; return 0; }
    sleep 1
  done
  err "Backend did not become healthy — check $LOGDIR/backend.log"; exit 1
}

# --- container runtime (docker OR native podman) ---------------------------
# Set by choose_runtime():
#   RT       = "docker" | "podman"
#   RT_CMD   = the base command, e.g. "docker" or "sudo podman"
#   RT_RUN   = extra flags for `run` (podman on old kernels needs seccomp off)
#   RT_HOST  = backend URL reachable from INSIDE a container
RT=""; RT_CMD=""; RT_RUN=""; RT_HOST=""

_docker_ok() { command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; }
_podman_cmd() {  # echoes a working podman invocation ("podman" or "sudo podman"), or nothing
  command -v podman >/dev/null 2>&1 || return 1
  if podman info >/dev/null 2>&1; then echo "podman"; return 0; fi
  if sudo -n podman info >/dev/null 2>&1; then echo "sudo podman"; return 0; fi
  # rootful podman usually needs sudo (may prompt once)
  if sudo podman info >/dev/null 2>&1; then echo "sudo podman"; return 0; fi
  return 1
}

# Host URL a container can use to reach the backend on this host.
_host_url() {
  if [ "$RT" = "docker" ]; then echo "http://host.docker.internal:$BACKEND_PORT/v1"; return; fi
  # podman: prefer the host's primary LAN IP (works on old podman without
  # host.containers.internal); fall back to that name on newer podman.
  ip="$( (hostname -I 2>/dev/null | awk '{print $1}') )"
  [ -n "$ip" ] && echo "http://$ip:$BACKEND_PORT/v1" || echo "http://host.containers.internal:$BACKEND_PORT/v1"
}

choose_runtime() {
  [ -n "$RT" ] && return 0   # already chosen
  local want="${IACI_RUNTIME:-}"
  local have_docker="" have_podman="" pcmd=""
  if _docker_ok; then have_docker=1; fi
  pcmd="$(_podman_cmd || true)"
  if [ -n "$pcmd" ]; then have_podman=1; fi

  if [ -z "$want" ]; then
    if [ -n "$have_docker" ] && [ -n "$have_podman" ] && [ -t 0 ]; then
      printf "\033[36m[iaci]\033[0m Container runtime — docker or podman? [docker]: " >&2
      read -r ans; want="${ans:-docker}"
    elif [ -n "$have_docker" ]; then want="docker"
    elif [ -n "$have_podman" ]; then want="podman"
    else
      err "No container runtime found. Install Docker, or on RHEL/CentOS: 'sudo yum install -y podman'. (Or choose the built-in UI: ./setup.sh react)"
      exit 1
    fi
  fi

  case "$want" in
    docker)
      [ -n "$have_docker" ] || { err "Docker selected but not available/running. Start Docker Desktop or set IACI_RUNTIME=podman."; exit 1; }
      RT=docker; RT_CMD=docker; RT_RUN="--add-host=host.docker.internal:host-gateway" ;;
    podman)
      [ -n "$have_podman" ] || { err "Podman selected but not available. 'sudo yum install -y podman' first."; exit 1; }
      RT=podman; RT_CMD="$pcmd"
      # Old runc/seccomp (RHEL 7) blocks clone3() -> "can't start new thread";
      # unconfined seccomp + unlimited pids make modern images run.
      RT_RUN="--security-opt seccomp=unconfined --pids-limit=0" ;;
    *) err "Unknown IACI_RUNTIME='$want' (use docker or podman)."; exit 1 ;;
  esac
  RT_HOST="$(_host_url)"
  log "Container runtime: $RT_CMD  (backend URL for containers: $RT_HOST)"
}

container_can_reach_backend() {
  # Verify the just-started container can reach the host backend (the #1 way
  # the OSS UIs "break"). Open WebUI & LibreChat both ship python3.
  local name="$1" url="${RT_HOST%/v1}/v1/models"
  for _ in $(seq 1 10); do
    if $RT_CMD exec "$name" python3 -c \
      "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('$url',timeout=5).status==200 else 1)" \
      >/dev/null 2>&1; then
      log "✓ $name can reach the IACI backend ($RT_HOST)"
      return 0
    fi
    sleep 2
  done
  warn "$name could not reach the backend yet. Give it a few seconds; if it persists,"
  warn "confirm the backend is on :$BACKEND_PORT and reachable at $RT_HOST."
}

# --- UIs -------------------------------------------------------------------
start_react() {
  require npm
  ( cd frontend
    [ -d node_modules ] || { log "Installing frontend dependencies…"; npm install; }
    printf 'REACT_APP_API_URL=http://localhost:%s\n' "$BACKEND_PORT" > .env.local
    if port_busy "$REACT_PORT"; then
      warn "Port $REACT_PORT busy — assuming the IACI UI is already running."
    else
      log "Starting IACI React UI on :$REACT_PORT…"
      PORT="$REACT_PORT" BROWSER=none nohup npm start >"$LOGDIR/frontend.log" 2>&1 &
    fi
  )
  log "→ IACI UI:  http://localhost:$REACT_PORT"
}

start_openwebui() {
  choose_runtime
  if port_busy "$OPENWEBUI_PORT"; then
    warn "Port $OPENWEBUI_PORT busy — set IACI_OPENWEBUI_PORT to a free port if this isn't Open WebUI."
  fi
  log "Starting Open WebUI on :$OPENWEBUI_PORT (first run pulls a ~6GB image)…"
  $RT_CMD rm -f iaci-openwebui >/dev/null 2>&1 || true
  $RT_CMD run -d $RT_RUN -p "$OPENWEBUI_PORT:8080" \
    -e OPENAI_API_BASE_URL="$RT_HOST" \
    -e OPENAI_API_KEY=iaci \
    -e WEBUI_AUTH=false \
    -e ENABLE_OLLAMA_API=false \
    -e WEBUI_NAME="IACI (Infoblox)" \
    -v iaci_openwebui:/app/backend/data \
    --name iaci-openwebui "${OPENWEBUI_IMAGE:-ghcr.io/open-webui/open-webui:main}" >/dev/null
  container_can_reach_backend iaci-openwebui
  log "→ Open WebUI:  http://localhost:$OPENWEBUI_PORT  (no login; model 'iaci-infoblox-wapi' is preselected)"
}

start_slack() {
  log "Installing Slack bot dependencies…"
  "$PY" -m pip install -q -r integrations/slack/requirements.txt
  if [ -z "${SLACK_BOT_TOKEN:-}" ] || [ -z "${SLACK_APP_TOKEN:-}" ]; then
    # Try to read them from .env if present.
    if [ -f .env ] && grep -q "SLACK_BOT_TOKEN" .env && grep -q "SLACK_APP_TOKEN" .env; then
      set -a; . ./.env; set +a
    fi
  fi
  if [ -z "${SLACK_BOT_TOKEN:-}" ] || [ -z "${SLACK_APP_TOKEN:-}" ]; then
    warn "Slack tokens not set. Create the app (see integrations/slack/README.md), then add to .env:"
    warn "  SLACK_BOT_TOKEN=xoxb-…   SLACK_APP_TOKEN=xapp-…   SLACK_WRITER_USERS=U123,U456"
    warn "…and re-run: ./setup.sh slack"
    return 0
  fi
  export IACI_API_URL="http://localhost:$BACKEND_PORT"
  log "Starting IACI Slack bot (Socket Mode)…"
  nohup "$PY" -m integrations.slack.app >"$LOGDIR/slack.log" 2>&1 &
  sleep 2
  log "→ Slack bot running (Socket Mode). Invite it to a channel and @mention it."
  log "   logs: $LOGDIR/slack.log"
}

start_teams() {
  log "Installing Teams bot dependencies…"
  "$PY" -m pip install -q -r integrations/teams/requirements.txt
  [ -f .env ] && { set -a; . ./.env; set +a; }
  if [ -z "${MicrosoftAppId:-}" ] || [ -z "${MicrosoftAppPassword:-}" ]; then
    warn "Teams app not configured. See integrations/teams/README.md, then add to .env:"
    warn "  MicrosoftAppId=…  MicrosoftAppPassword=…  TEAMS_WRITER_USERS=…"
    warn "…and re-run: ./setup.sh teams"
    return 0
  fi
  export IACI_API_URL="http://localhost:$BACKEND_PORT"
  log "Starting IACI Teams bot on :3978 (POST /api/messages)…"
  nohup "$PY" -m integrations.teams.app >"$LOGDIR/teams.log" 2>&1 &
  sleep 2
  log "→ Teams bot on :3978. Expose it (e.g. 'ngrok http 3978') and set that https URL"
  log "   as the bot's Messaging endpoint (…/api/messages). logs: $LOGDIR/teams.log"
}

start_whatsapp() {
  log "Installing WhatsApp bot dependencies…"
  "$PY" -m pip install -q -r integrations/whatsapp/requirements.txt
  [ -f .env ] && { set -a; . ./.env; set +a; }
  if [ -z "${WHATSAPP_TOKEN:-}" ] || [ -z "${WHATSAPP_PHONE_NUMBER_ID:-}" ]; then
    warn "WhatsApp Cloud API not configured. See integrations/whatsapp/README.md, then add to .env:"
    warn "  WHATSAPP_TOKEN=…  WHATSAPP_PHONE_NUMBER_ID=…  WHATSAPP_VERIFY_TOKEN=…  WHATSAPP_WRITER_USERS=…"
    warn "…and re-run: ./setup.sh whatsapp"
    return 0
  fi
  export IACI_API_URL="http://localhost:$BACKEND_PORT"
  log "Starting IACI WhatsApp bot on :8088 (/webhook)…"
  nohup "$PY" -m integrations.whatsapp.app >"$LOGDIR/whatsapp.log" 2>&1 &
  sleep 2
  log "→ WhatsApp webhook on :8088. Expose it (e.g. 'ngrok http 8088') and set that https"
  log "   URL (…/webhook) in the Meta webhook config. logs: $LOGDIR/whatsapp.log"
}

start_librechat() {
  choose_runtime
  if [ ! -f librechat/.env ]; then
    require openssl
    log "Generating LibreChat secrets (librechat/.env)…"
    {
      echo "HOST=0.0.0.0"; echo "PORT=3080"
      echo "MONGO_URI=mongodb://mongodb:27017/LibreChat"
      echo "CONFIG_PATH=/app/librechat.yaml"
      echo "ALLOW_REGISTRATION=true"; echo "ALLOW_EMAIL_LOGIN=true"; echo "SEARCH=false"
      echo "CREDS_KEY=$(openssl rand -hex 32)"; echo "CREDS_IV=$(openssl rand -hex 16)"
      echo "JWT_SECRET=$(openssl rand -hex 32)"; echo "JWT_REFRESH_SECRET=$(openssl rand -hex 32)"
    } > librechat/.env
  fi
  # Point LibreChat's custom endpoint at the backend URL containers can reach.
  sed -i.bak "s#baseURL:.*#baseURL: \"$RT_HOST\"#" librechat/librechat.yaml
  rm -f librechat/librechat.yaml.bak
  log "Starting LibreChat on :$LIBRECHAT_PORT (first run pulls images)…"

  if [ "$RT" = "docker" ]; then
    ( cd librechat && LIBRECHAT_PORT="$LIBRECHAT_PORT" docker compose up -d )
  else
    # No compose on bare podman → run mongo + app in a shared pod (localhost).
    local mongo_uri="mongodb://localhost:27017/LibreChat"
    $RT_CMD pod rm -f iaci-lc >/dev/null 2>&1 || true
    $RT_CMD pod create --name iaci-lc -p "$LIBRECHAT_PORT:3080" >/dev/null
    $RT_CMD run -d --pod iaci-lc $RT_RUN --name iaci-lc-mongo \
      docker.io/library/mongo:7 mongod --quiet >/dev/null
    # Override MONGO_URI to the pod's localhost mongo (the compose .env points at "mongodb").
    $RT_CMD run -d --pod iaci-lc $RT_RUN --env-file librechat/.env -e "MONGO_URI=$mongo_uri" \
      -v "$PWD/librechat/librechat.yaml:/app/librechat.yaml:ro" \
      --name iaci-librechat ghcr.io/danny-avila/librechat:latest >/dev/null
  fi
  container_can_reach_backend iaci-librechat
  log "→ LibreChat:  http://localhost:$LIBRECHAT_PORT  (register a local account, then pick the 'IACI' endpoint)"
}

# --- stop ------------------------------------------------------------------
# Kill whatever is listening on a port — uses lsof or ss if present, else a
# pattern match. Avoids a hard lsof dependency (RHEL minimal images lack it).
kill_port() {
  if command -v lsof >/dev/null 2>&1; then lsof -ti:"$1" 2>/dev/null | xargs -r kill -9 2>/dev/null || true; return; fi
  if command -v fuser >/dev/null 2>&1; then fuser -k "$1"/tcp >/dev/null 2>&1 || true; return; fi
}

do_stop() {
  log "Stopping IACI services…"
  kill_port "$BACKEND_PORT"; pkill -f "backend[.]app" 2>/dev/null || true
  kill_port "$REACT_PORT";   pkill -f "react-scripts" 2>/dev/null || true
  pkill -f "integrations[.]slack[.]app" 2>/dev/null || true
  pkill -f "integrations[.]teams[.]app" 2>/dev/null || true
  pkill -f "integrations[.]whatsapp[.]app" 2>/dev/null || true
  # Tear down OSS-UI containers under whichever runtime is present.
  for c in docker "podman" "sudo podman"; do
    command -v "${c##* }" >/dev/null 2>&1 || continue
    $c rm -f iaci-openwebui >/dev/null 2>&1 || true
    $c pod rm -f iaci-lc >/dev/null 2>&1 || true   # podman LibreChat pod
  done
  if [ -f librechat/docker-compose.yml ] && command -v docker >/dev/null 2>&1; then
    ( cd librechat && docker compose down >/dev/null 2>&1 || true )
  fi
  log "Stopped. (Container images/volumes are kept.)"
}

# --- main ------------------------------------------------------------------
choice="${1:-}"
if [ "$choice" = "stop" ]; then do_stop; exit 0; fi

if [ -z "$choice" ]; then
  echo ""
  echo "Which interface do you want to run? (the backend always runs)"
  echo "  1) IACI built-in React UI   — no extra installs, recommended"
  echo "  2) Open WebUI               — polished, Docker image ~6GB"
  echo "  3) LibreChat                — most features, Docker + MongoDB ~4GB"
  echo "  4) Slack bot                — team chatbot (Socket Mode, approval buttons)"
  echo "  5) Microsoft Teams bot      — team chatbot (Bot Framework, Adaptive Cards)"
  echo "  6) WhatsApp bot             — team chatbot (Meta Cloud API)"
  echo "  7) Backend only             — use the API / your own OpenAI-compatible client"
  echo ""
  printf "Select [1-7] (default 1): "
  read -r ans
  case "$ans" in
    2) choice=openwebui;; 3) choice=librechat;; 4) choice=slack;;
    5) choice=teams;; 6) choice=whatsapp;; 7) choice=none;; *) choice=react;;
  esac
fi

setup_backend
start_backend

case "$choice" in
  react)     start_react ;;
  openwebui) start_openwebui ;;
  librechat) start_librechat ;;
  slack)     start_slack ;;
  teams)     start_teams ;;
  whatsapp)  start_whatsapp ;;
  none)      log "Backend only. API at http://localhost:$BACKEND_PORT (OpenAI-compatible at /v1)." ;;
  *)         err "Unknown option '$choice' (use: react|openwebui|librechat|slack|teams|whatsapp|none|stop)"; exit 1 ;;
esac

echo ""
log "Backend API:  http://localhost:$BACKEND_PORT   (health: /api/health, status: /api/status)"
log "Logs:         $LOGDIR/   |   Stop everything:  ./setup.sh stop"
