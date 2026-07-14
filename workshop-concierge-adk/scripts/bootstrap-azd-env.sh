#!/usr/bin/env bash
# Bootstrap the ISOLATED agent azd environment (wc-dev) from the landing-zone
# outputs — WITHOUT modifying the infra project or its pha-dev environment.
#
# Safe by construction: reads infra values with `azd env get-value` run *inside*
# ../landing-zone, then writes them into the agent env with `azd env set` run
# *inside* this directory. The two azd projects never share state.
#
# Usage:  ./scripts/bootstrap-azd-env.sh [agent_env_name]   (default: wc-dev)
set -euo pipefail

AGENT_ENV="${1:-wc-dev}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$(cd "$HERE/../landing-zone" && pwd)"

echo "Agent project : $HERE  (env: $AGENT_ENV)"
echo "Infra project : $INFRA_DIR (env: pha-dev, read-only)"

# --- read infra outputs (read-only; never mutates the infra env) -------------
infra_get() {
  ( cd "$INFRA_DIR" && azd env get-value "$1" 2>/dev/null || true )
}

SUB="$(infra_get AZURE_SUBSCRIPTION_ID)"
RG="$(infra_get AZURE_RESOURCE_GROUP)"
LOC="$(infra_get AZURE_LOCATION)"
TENANT="$(infra_get TENANT_ID)"

# --- create/select the isolated agent env ------------------------------------
cd "$HERE"
if ! azd env list --output json 2>/dev/null | grep -q "\"Name\": *\"$AGENT_ENV\""; then
  azd env new "$AGENT_ENV" --no-prompt \
    ${SUB:+--subscription "$SUB"} ${LOC:+--location "$LOC"}
fi
azd env select "$AGENT_ENV"

# --- write shared handles into the agent env ---------------------------------
[ -n "$SUB" ]    && azd env set AZURE_SUBSCRIPTION_ID "$SUB"
[ -n "$RG" ]     && azd env set AZURE_RESOURCE_GROUP "$RG"
[ -n "$LOC" ]    && azd env set AZURE_LOCATION "$LOC"
[ -n "$TENANT" ] && azd env set AZURE_TENANT_ID "$TENANT"

# Agent-specific config (override as needed).
azd env set MODEL_DEPLOYMENT_NAME "${MODEL_DEPLOYMENT_NAME:-chat}"
azd env set AZURE_OPENAI_API_VERSION "${AZURE_OPENAI_API_VERSION:-2025-04-01-preview}"

echo
echo "Agent env '$AGENT_ENV' bootstrapped. Verify with: azd env get-values"
echo "Infra env 'pha-dev' left untouched."
