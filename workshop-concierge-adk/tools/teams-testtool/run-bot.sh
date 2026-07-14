#!/usr/bin/env bash
# Start the LOCAL, TEST-ONLY Bot Framework messaging host for the Teams App Test Tool.
# Serves POST /api/messages (+ /api/proactive, /health) on :3978. No Azure, no auth,
# no tunnel. NEVER deployed — see ./README.md and ../../KNOWN-ISSUES.md #1.
set -euo pipefail

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$TOOL_DIR/../.." && pwd)"   # workshop-concierge-adk/
cd "$ROOT"

# Reuse the repo virtualenv if present; otherwise create a throwaway one and install
# the test-only deps (aiohttp + pyyaml for the catalog).
VENV="${VENV:-$ROOT/.venv}"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Creating virtualenv at $VENV ..."
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -c "import aiohttp, yaml" 2>/dev/null || pip install -q -r "$TOOL_DIR/requirements.txt" pyyaml

export PYTHONPATH="$ROOT/src"
export WORKSHOP_CATALOG_DIR="$ROOT/catalog"
export BOT_PORT="${BOT_PORT:-3978}"

echo "Bot host → http://localhost:${BOT_PORT}/api/messages  (LOCAL TEST ONLY)"
exec python "$TOOL_DIR/host.py"
