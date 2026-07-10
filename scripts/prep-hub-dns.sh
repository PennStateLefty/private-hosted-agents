#!/usr/bin/env bash
# prep-hub-dns.sh — OPTIONAL centralized-DNS path.
# Pre-creates the private DNS zones that a private Foundry + Agent Service + APIM
# gateway need but that are MISSING from the hub, links each to the hub VNet (so
# P2S VPN clients resolve them), and prints BYO resource IDs to feed into
# configure-azd-env.sh (EXISTING_PRIVATE_DNS_ZONE_*_RESOURCE_ID).
#
# Idempotent. Creates cloud state (DNS zones + VNet links) — low cost, reversible.
set -euo pipefail

SUB="987a5b92-2573-4981-a76c-bbd7756592c8"
DNS_RG="rg-mcaps-dns-dev"
HUB_VNET_ID="/subscriptions/${SUB}/resourceGroups/rg-mcaps-hub-dev/providers/Microsoft.Network/virtualNetworks/vnet-mcaps-hub-dev"

az account set --subscription "$SUB"

# zone-name|BYO env-var suffix  (bash 3.2 compatible — no associative arrays)
ZONES="
privatelink.cognitiveservices.azure.com|COGSVCS
privatelink.openai.azure.com|OPENAI
privatelink.services.ai.azure.com|AISERVICES
privatelink.search.windows.net|SEARCH
privatelink.documents.azure.com|COSMOS
privatelink.azconfig.io|APPCONFIG
privatelink.azurecontainerapps.io|CONTAINERAPPS
privatelink.monitor.azure.com|AZUREMONITOR
privatelink.oms.opinsights.azure.com|OMSOPSINSIGHTS
privatelink.ods.opinsights.azure.com|ODSOPSINSIGHTS
privatelink.agentsvc.azure-automation.net|AZUREAUTOMATION
privatelink.applicationinsights.azure.com|APPINSIGHTS
"

echo "# Paste these into configure-azd-env.sh (BYO DNS) or export before provisioning:"
echo "$ZONES" | while IFS='|' read -r zone suffix; do
  [ -z "$zone" ] && continue
  az network private-dns zone create -g "$DNS_RG" -n "$zone" -o none 2>/dev/null || true
  az network private-dns link vnet create -g "$DNS_RG" -z "$zone" \
    -n "link-hub" --virtual-network "$HUB_VNET_ID" --registration-enabled false -o none 2>/dev/null || true
  id="/subscriptions/${SUB}/resourceGroups/${DNS_RG}/providers/Microsoft.Network/privateDnsZones/${zone}"
  echo "azd env set EXISTING_PRIVATE_DNS_ZONE_${suffix}_RESOURCE_ID \"${id}\""
done
echo "# APIM gateway zone (Phase 1 aigateway) — created but no BYO param in the LZ:"
az network private-dns zone create -g "$DNS_RG" -n "privatelink.azure-api.net" -o none 2>/dev/null || true
az network private-dns link vnet create -g "$DNS_RG" -z "privatelink.azure-api.net" \
  -n "link-hub" --virtual-network "$HUB_VNET_ID" --registration-enabled false -o none 2>/dev/null || true
