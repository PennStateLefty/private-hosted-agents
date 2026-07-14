#!/usr/bin/env bash
# enable-activity-protocol.sh — Turn on the Bot Framework `activity` protocol on the
# Foundry Hosted Agent so Teams / M365 Copilot channel adapters can exchange messages.
#
# This is Step 3 of the Foundry private-network publish guide:
#   https://learn.microsoft.com/azure/foundry/agents/how-to/publish-copilot-virtual-network
# The publish API (publish-m365.sh) also does this automatically, but running it
# explicitly lets you test message delivery before publishing.
#
# It ADDS `activity` alongside `responses`, and `BotServiceRbac` alongside `Entra`.
# Removing `responses`/`Entra` would break the Foundry portal/SDK — we keep them.
#
# Requires: az login to the sub with the Foundry resource, Foundry User on the project.
set -euo pipefail

ENDPOINT="${FOUNDRY_PROJECT_ENDPOINT:?set FOUNDRY_PROJECT_ENDPOINT to https://<res>.services.ai.azure.com/api/projects/<proj>}"
AGENT_NAME="${AGENT_NAME:-workshop-concierge}"
# BotServiceRbac (Shared/Personal scope) or BotServiceTenant (Tenant scope) — must match
# the publishScope used in publish-m365.sh.
BOT_AUTH_SCHEME="${BOT_AUTH_SCHEME:-BotServiceRbac}"

TOKEN="$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)"

echo "==> Enabling 'activity' protocol + ${BOT_AUTH_SCHEME} on agent '${AGENT_NAME}'"
curl -sS -X PATCH \
  "${ENDPOINT}/agents/${AGENT_NAME}?api-version=v1" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/merge-patch+json" \
  -H "Foundry-Features: AgentEndpoints=V1Preview" \
  -d @- <<JSON | python3 -m json.tool
{
  "agent_endpoint": {
    "protocols": ["responses", "activity"],
    "authorization_schemes": [
      { "type": "Entra", "isolation_key_source": { "kind": "Entra" } },
      { "type": "${BOT_AUTH_SCHEME}" }
    ]
  }
}
JSON

echo "==> Done. Verify with:"
echo "   curl -s \"${ENDPOINT}/agents/${AGENT_NAME}?api-version=v1\" -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool | grep -A6 protocols"
