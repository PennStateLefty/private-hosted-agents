#!/usr/bin/env bash
# Trigger the agent to PROACTIVELY open/continue a chat in the Agents Playground —
# no inbound message required. Thin curl wrapper over POST /api/proactive on the
# running host (./run-bot.sh or ./run-bot-agent.sh). LOCAL TEST ONLY.
#
# Usage:
#   ./trigger-proactive.sh                     # default opener (agent greeting / intake card)
#   ./trigger-proactive.sh "hi there"          # send literal text
#   PROMPT="I'm a developer, recommend a track" ./trigger-proactive.sh
#                                              # agent mode: real agent authors the opener
#   CONVERSATION_ID=abc SERVICE_URL=http://localhost:56150 ./trigger-proactive.sh
#                                              # COLD start: open a chat the user hasn't messaged
#
# Env:
#   BOT_URL          host base URL            (default http://localhost:3978)
#   CONVERSATION_ID  target conversation id   (default: most recent seen by the host)
#   SERVICE_URL      Playground connector URL (required only for a cold start)
#   USER_ID/BOT_ID   ids for a cold start     (default user-1 / workshop-concierge)
#   PROMPT           agent-mode opener prompt (agent mode only)
set -euo pipefail

BOT_URL="${BOT_URL:-http://localhost:3978}"
TEXT="${1:-}"

# Build the JSON body from whatever env/args are provided.
body='{}'
add() { body="$(python3 -c "import json,sys;d=json.loads(sys.argv[1]);d[sys.argv[2]]=sys.argv[3];print(json.dumps(d))" "$body" "$1" "$2")"; }

[[ -n "$TEXT" ]]                        && add text "$TEXT"
[[ -n "${PROMPT:-}" ]]                  && add prompt "$PROMPT"
[[ -n "${CONVERSATION_ID:-}" ]]         && add conversationId "$CONVERSATION_ID"
[[ -n "${SERVICE_URL:-}" ]]             && add serviceUrl "$SERVICE_URL"
[[ -n "${USER_ID:-}" ]]                 && add userId "$USER_ID"
[[ -n "${BOT_ID:-}" ]]                  && add botId "$BOT_ID"

echo "POST ${BOT_URL}/api/proactive  ${body}"
curl -sS -X POST "${BOT_URL}/api/proactive" \
  -H 'content-type: application/json' \
  -d "$body"
echo
