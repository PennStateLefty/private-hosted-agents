#!/usr/bin/env bash
# publish-m365.sh — Create the Azure Bot resource pointing at the Foundry agent's activity
# protocol endpoint (via the App Gateway public FQDN), then publish the agent to Microsoft
# 365 Copilot & Teams with the Foundry Microsoft 365 publish API.
#
# Foundry-native path (NO custom bot host):
#   Steps 2 + 4 of https://learn.microsoft.com/azure/foundry/agents/how-to/publish-copilot-virtual-network
#   The Azure Bot `endpoint` is the App Gateway FQDN carrying the agent activityProtocol
#   path; App Gateway reverse-proxies to the agent PRIVATE endpoint (see app-gateway.bicep).
#
# DEPLOY-GATED: requires PUBLIC_INGRESS_ENABLED=true (sanctioned exception, ADR-001), plus a
# deployed App Gateway (MESSAGING_ENDPOINT) and a TLS cert on its listener.
set -euo pipefail

if [[ "${PUBLIC_INGRESS_ENABLED:-false}" != "true" ]]; then
  echo "REFUSING: PUBLIC_INGRESS_ENABLED != true (sanctioned public-ingress exception, ADR-001)." >&2
  exit 2
fi

RG="${AZURE_RESOURCE_GROUP:-rg-pha-dev}"
ENDPOINT="${FOUNDRY_PROJECT_ENDPOINT:?set FOUNDRY_PROJECT_ENDPOINT}"
AGENT_NAME="${AGENT_NAME:-workshop-concierge}"
TENANT_ID="${AZURE_TENANT_ID:-$(az account show --query tenantId -o tsv)}"
BOT_NAME="${BOT_NAME:-bot-workshop-concierge-pha-dev}"
LAW_ID="${LAW_ID:-}"
# The App Gateway public messaging endpoint (from app-gateway.bicep output messagingEndpoint):
#   https://<agw-fqdn>/api/projects/<proj>/agents/<agent>/endpoint/protocols/activityProtocol?api-version=2025-05-15-preview
MESSAGING_ENDPOINT="${MESSAGING_ENDPOINT:?set MESSAGING_ENDPOINT to the App Gateway FQDN + activityProtocol path}"
# Shared (Just you) -> BotServiceRbac ; Tenant (org-wide, needs M365 admin approval) -> BotServiceTenant
PUBLISH_SCOPE="${PUBLISH_SCOPE:-Shared}"
APP_VERSION="${APP_VERSION:-1.0.0}"

TOKEN="$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)"

echo "==> 1/4 Get agent identity principal id"
PRINCIPAL_ID="$(curl -sS "${ENDPOINT}/agents/${AGENT_NAME}?api-version=v1" \
  -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["instance_identity"]["principal_id"])')"
echo "   agent principal_id: ${PRINCIPAL_ID}"

# Agent activityProtocol endpoint (the value the Bot resource proxies to via App Gateway).
ACTIVITY_ENDPOINT="${ENDPOINT}/agents/${AGENT_NAME}/endpoint/protocols/activityProtocol?api-version=2025-05-15-preview"

echo "==> 2/4 Deploy Azure Bot + Teams channel (endpoint = App Gateway FQDN)"
az deployment group create \
  --resource-group "$RG" \
  --template-file "$(cd "$(dirname "$0")/.." && pwd)/infra/bot/bot-service.bicep" \
  --parameters \
      botName="$BOT_NAME" \
      messagingEndpoint="$MESSAGING_ENDPOINT" \
      msaAppId="$PRINCIPAL_ID" \
      msaAppType=SingleTenant \
      msaAppTenantId="$TENANT_ID" \
      logAnalyticsWorkspaceId="$LAW_ID" \
  --query "properties.provisioningState" -o tsv

BOT_ARM_ID="$(az bot show --name "$BOT_NAME" --resource-group "$RG" --query id -o tsv)"
echo "   bot arm id: ${BOT_ARM_ID}"
echo "   NOTE: activityProtocol endpoint the App Gateway must reach = ${ACTIVITY_ENDPOINT}"

echo "==> 3/4 Publish to Microsoft 365 (scope=${PUBLISH_SCOPE}, version=${APP_VERSION})"
curl -sS -X POST \
  "${ENDPOINT}/agents/${AGENT_NAME}/microsoft365/publish?api-version=v1" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d @- <<JSON | python3 -m json.tool
{
  "agentDisplayName": "Workshop Concierge",
  "botServiceArmId": "${BOT_ARM_ID}",
  "publishScope": "${PUBLISH_SCOPE}",
  "publishAsAutopilot": false,
  "appVersion": "${APP_VERSION}",
  "shortDescription": "Workshop logistics concierge (Foundry Hosted Agent).",
  "fullDescription": "Answers workshop schedule, room, and prerequisite questions. Runs privately in the MCAPS landing zone; published to Teams via a WAF-fronted App Gateway.",
  "developerName": "MCAPS Private Hosted Agents",
  "developerWebsiteUrl": "https://azure.microsoft.com",
  "privacyUrl": "https://privacy.microsoft.com",
  "termsOfUseUrl": "https://www.microsoft.com/legal/terms-of-use"
}
JSON

echo "==> 4/4 Done."
cat <<NEXT
- Shared scope: the agent appears under "Your agents" in the M365/Teams store (may take ~1h).
- Tenant scope: a Microsoft 365 admin must approve it at
    https://admin.cloud.microsoft/#/agents/all/requested
- Verify the inbound path: send a message in Teams; a reply proves channel adapter ->
  App Gateway -> Foundry private endpoint -> agent, and the reply path back out.
NEXT
