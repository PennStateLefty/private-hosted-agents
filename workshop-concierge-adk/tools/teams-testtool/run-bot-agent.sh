#!/usr/bin/env bash
# Start the LOCAL, TEST-ONLY bot host in AGENT mode: it runs the REAL Google ADK
# agent (src/workshop_concierge/agent.py) locally and calls the models ALREADY
# DEPLOYED in Foundry (Azure OpenAI), then prints OpenTelemetry spans to this terminal
# so you can watch the agent orchestrate each response.
#
# Local everything except the model: Teams sim (Agents Playground) local, bot service
# local (:3978), agent local — model calls go to Foundry over your VPN using your
# Azure identity (DefaultAzureCredential). No M365 license, no Azure Bot, no tunnel.
#
# Requires:
#   * Python 3.13 venv at ./.venv-agent (google-adk/litellm won't install on 3.14).
#   * VPN up + `az login` with `Cognitive Services OpenAI User` on the Foundry account.
#   * Foundry endpoint/deployment values (auto-sourced from the azd env, see below).
set -euo pipefail

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$TOOL_DIR/../.." && pwd)"   # workshop-concierge-adk/
cd "$ROOT"

# --- Python 3.13 agent venv -------------------------------------------------
VENV="${WC_AGENT_VENV:-$ROOT/.venv-agent}"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "ERROR: agent venv not found at $VENV" >&2
  echo "Create it with Python 3.13 and install the agent deps:" >&2
  echo "  /opt/homebrew/bin/python3.13 -m venv $VENV" >&2
  echo "  $VENV/bin/pip install -r $TOOL_DIR/requirements-agent.txt" >&2
  exit 1
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# --- Foundry model env ------------------------------------------------------
# Source the endpoint/deployment/api-version from the azd env of the MAIN checkout
# (the worktree intentionally omits .azure). Override the file with WC_AZURE_ENV_FILE,
# or just pre-export AZURE_OPENAI_ENDPOINT / MODEL_DEPLOYMENT_NAME / AZURE_OPENAI_API_VERSION.
DEFAULT_ENV_FILE="/Users/jeremiahgutherie/Development/pennstatelefty-org/private-hosted-agents/workshop-concierge-adk/.azure/wc-dev/.env"
AZURE_ENV_FILE="${WC_AZURE_ENV_FILE:-$DEFAULT_ENV_FILE}"

_load_key() {
  # _load_key KEY FILE -> echoes the unquoted value of KEY from a dotenv file
  local key="$1" file="$2"
  [[ -f "$file" ]] || return 0
  local line
  line="$(grep -E "^${key}=" "$file" | tail -n1 || true)"
  [[ -n "$line" ]] || return 0
  local val="${line#*=}"
  val="${val%\"}"; val="${val#\"}"   # strip surrounding double quotes
  printf '%s' "$val"
}

if [[ -f "$AZURE_ENV_FILE" ]]; then
  echo "Sourcing Foundry model env from: $AZURE_ENV_FILE"
  for K in AZURE_OPENAI_ENDPOINT MODEL_DEPLOYMENT_NAME AZURE_OPENAI_API_VERSION FOUNDRY_PROJECT_ENDPOINT; do
    if [[ -z "${!K:-}" ]]; then
      V="$(_load_key "$K" "$AZURE_ENV_FILE")"
      [[ -n "$V" ]] && export "$K=$V"
    fi
  done
else
  echo "NOTE: azd env file not found at $AZURE_ENV_FILE — relying on pre-exported AZURE_OPENAI_* vars." >&2
fi

if [[ -z "${AZURE_OPENAI_ENDPOINT:-}" && -z "${FOUNDRY_PROJECT_ENDPOINT:-}" ]]; then
  echo "ERROR: no AZURE_OPENAI_ENDPOINT (or FOUNDRY_PROJECT_ENDPOINT) set — cannot reach the Foundry model." >&2
  exit 1
fi

# --- Host config ------------------------------------------------------------
export PYTHONPATH="$ROOT/src"
export WORKSHOP_CATALOG_DIR="$ROOT/catalog"
export BOT_PORT="${BOT_PORT:-3978}"
export WC_HOST_MODE=agent
export WC_TELEMETRY="${WC_TELEMETRY:-console}"
# WC_MODEL=stub builds the agent without calling the network (import/telemetry check).
export WC_MODEL="${WC_MODEL:-}"

echo "Bot host (AGENT mode) → http://localhost:${BOT_PORT}/api/messages"
echo "  model endpoint : ${AZURE_OPENAI_ENDPOINT:-<derived from FOUNDRY_PROJECT_ENDPOINT>}"
echo "  deployment     : ${MODEL_DEPLOYMENT_NAME:-chat}"
echo "  telemetry      : ${WC_TELEMETRY} (spans print below)"
echo "  python         : $(python --version 2>&1)  venv=$VENV"
exec python "$TOOL_DIR/host.py"
