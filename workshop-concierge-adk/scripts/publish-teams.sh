#!/usr/bin/env bash
# publish-teams.sh — Orchestrate the Foundry-native Teams / M365 publish for the Workshop
# Concierge Hosted Agent. Supersedes the old custom-adapter + manual-manifest flow.
#
# CORRECTED ARCHITECTURE (no custom bot host — Foundry serves the activity protocol itself):
#   Teams -> Bot Channel Adapter -> Azure Bot -> App Gateway (public IP + TLS + WAF)
#         -> Foundry agent PRIVATE endpoint (services.ai.azure.com) -> Hosted Agent.
# See architecture/decisions/ADR-001-teams-public-ingress.md and evidence/G3-teams-publish.md.
#
# DEPLOY-GATED: the whole flow creates a PUBLIC IP and is a sanctioned exception. It refuses
# to run unless PUBLIC_INGRESS_ENABLED=true, and it needs a TLS cert (SSL_CERT_KV_SECRET_ID)
# plus an AGW identity (AGW_UAMI_ID) and a pre-created AGW subnet (APPGW_SUBNET_ID).
set -euo pipefail

if [[ "${PUBLIC_INGRESS_ENABLED:-false}" != "true" ]]; then
  cat >&2 <<'GATE'
BLOCKED: PUBLIC_INGRESS_ENABLED != true.

G3 (Teams delivery) requires public ingress, which is a sanctioned MCAPS exception in this
landing zone (network isolation is the default). Before running:
  1. Obtain the MCAPS public-ingress policy exception (ADR-001).
  2. Provision a TLS certificate for the App Gateway listener FQDN into Key Vault.
  3. Export PUBLIC_INGRESS_ENABLED=true and the AGW_* / SSL_CERT_* variables below.
GATE
  exit 2
fi

HERE="$(cd "$(dirname "$0")/.." && pwd)"
RG="${AZURE_RESOURCE_GROUP:-rg-pha-dev}"
LOCATION="${AZURE_LOCATION:-northcentralus}"
FOUNDRY_FQDN="${FOUNDRY_BACKEND_FQDN:-aif-zliorc-pha-dev-ncus-001.services.ai.azure.com}"
PROJECT="${AZURE_AI_PROJECT_NAME:-aifp-zliorc-pha-dev-ncus-001}"
AGENT_NAME="${AGENT_NAME:-workshop-concierge}"
ACTIVITY_PATH="/api/projects/${PROJECT}/agents/${AGENT_NAME}/endpoint/protocols/activityProtocol?api-version=2025-05-15-preview"

: "${APPGW_SUBNET_ID:?set APPGW_SUBNET_ID (run scripts/create-appgw-subnet.sh first)}"
: "${SSL_CERT_KV_SECRET_ID:?set SSL_CERT_KV_SECRET_ID to the Key Vault cert secret id}"
: "${AGW_UAMI_ID:?set AGW_UAMI_ID to the AGW user-assigned identity resourceId}"
LAW_ID="${LAW_ID:-}"
LISTENER_HOST="${LISTENER_HOST:-}"

echo "==> 1/3 Enable activity protocol on the agent"
FOUNDRY_PROJECT_ENDPOINT="https://${FOUNDRY_FQDN}/api/projects/${PROJECT}" \
  AGENT_NAME="$AGENT_NAME" "$HERE/scripts/enable-activity-protocol.sh"

echo "==> 2/3 Deploy App Gateway (public ingress -> Foundry private endpoint)"
MSG_ENDPOINT="$(az deployment group create \
  --resource-group "$RG" \
  --template-file "$HERE/infra/bot/app-gateway.bicep" \
  --parameters \
      name="agw-teams-pha-dev" \
      location="$LOCATION" \
      subnetResourceId="$APPGW_SUBNET_ID" \
      foundryBackendFqdn="$FOUNDRY_FQDN" \
      listenerHostName="$LISTENER_HOST" \
      sslCertKeyVaultSecretId="$SSL_CERT_KV_SECRET_ID" \
      userAssignedIdentityId="$AGW_UAMI_ID" \
      activityProtocolPath="$ACTIVITY_PATH" \
      logAnalyticsWorkspaceId="$LAW_ID" \
  --query "properties.outputs.messagingEndpoint.value" -o tsv)"
echo "   messaging endpoint: ${MSG_ENDPOINT}"

echo "==> 3/3 Create Azure Bot + publish to M365/Teams"
MESSAGING_ENDPOINT="$MSG_ENDPOINT" \
  FOUNDRY_PROJECT_ENDPOINT="https://${FOUNDRY_FQDN}/api/projects/${PROJECT}" \
  AGENT_NAME="$AGENT_NAME" LAW_ID="$LAW_ID" "$HERE/scripts/publish-m365.sh"

echo "==> Orchestration complete. Verify delivery in Teams (see publish-m365.sh output)."
