#!/usr/bin/env bash
# Grant the hosted agent's instance managed identity the data-plane role it needs
# to call the Foundry model over Entra (no keys). The instance identity only exists
# AFTER `azd deploy`, so this runs as a post-deploy step (idempotent).
#
# Why: the ADK adapter authenticates the model with DefaultAzureCredential, which in
# the container resolves to the injected instance managed identity (IMDS). Without
# "Cognitive Services OpenAI User" on the Foundry account, model calls fail with:
#   AuthenticationError ... lacks the required data action
#   Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action
set -euo pipefail

SUB="${AZURE_SUBSCRIPTION_ID:-987a5b92-2573-4981-a76c-bbd7756592c8}"
ACCOUNT_RG="${AZURE_RESOURCE_GROUP:-rg-pha-dev}"
ACCOUNT_NAME="${AZURE_AI_ACCOUNT_NAME:-aif-zliorc-pha-dev-ncus-001}"
AGENT_SERVICE="${1:-workshop-concierge}"

az account set --subscription "$SUB"
ACCT_ID="/subscriptions/${SUB}/resourceGroups/${ACCOUNT_RG}/providers/Microsoft.CognitiveServices/accounts/${ACCOUNT_NAME}"

echo "==> Resolving instance identity for agent '${AGENT_SERVICE}' via azd ai agent show"
SHOW="$(azd ai agent show "$AGENT_SERVICE" 2>/dev/null || true)"
INSTANCE_PID="$(echo "$SHOW" | awk -F'  +' '/Instance Identity Principal ID/{print $2}' | tr -d '[:space:]')"
BLUEPRINT_PID="$(echo "$SHOW" | awk -F'  +' '/Blueprint Principal ID/{print $2}' | tr -d '[:space:]')"

if [[ -z "$INSTANCE_PID" ]]; then
  echo "ERROR: could not resolve Instance Identity Principal ID (is the agent deployed?)"; exit 1
fi

for PID in "$INSTANCE_PID" "$BLUEPRINT_PID"; do
  [[ -z "$PID" ]] && continue
  echo "    grant 'Cognitive Services OpenAI User' -> ${PID}"
  az role assignment create \
    --assignee-object-id "$PID" --assignee-principal-type ServicePrincipal \
    --role "Cognitive Services OpenAI User" --scope "$ACCT_ID" -o none 2>/dev/null || true
done

echo "Done. Data-plane RBAC can take a couple minutes to propagate before the first"
echo "model call succeeds. Verify with: azd ai agent invoke ${AGENT_SERVICE} '<payload>'"
