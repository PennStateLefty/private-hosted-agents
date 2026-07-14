#!/usr/bin/env bash
# Run the Responses adapter locally (serves /responses + /readiness on :8088).
# Requires the private network (P2S VPN) + `az login` for the model call to
# succeed, since the Foundry account has public network access disabled.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

: "${FOUNDRY_PROJECT_ENDPOINT:=https://aif-zliorc-pha-dev-ncus-001.services.ai.azure.com/api/projects/aifp-zliorc-pha-dev-ncus-001}"
: "${MODEL_DEPLOYMENT_NAME:=chat}"
export FOUNDRY_PROJECT_ENDPOINT MODEL_DEPLOYMENT_NAME
export PYTHONPATH="$HERE/src"
export WORKSHOP_CATALOG_DIR="$HERE/catalog"

exec python -m adapter.app
