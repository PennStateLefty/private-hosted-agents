#!/usr/bin/env bash
# configure-azd-env.sh — Phase 1 azd env config for the private hosted-agents spoke,
# integrated into the existing mcaps-foundation hub.
#
# Prereq: run these first (see PROVISION.md):
#   cd landing-zone
#   azd auth login
#   azd env new pha-dev --subscription 987a5b92-2573-4981-a76c-bbd7756592c8 --location northcentralus
# Then run this script from the landing-zone/ dir:  ../scripts/configure-azd-env.sh
set -euo pipefail

SUB="987a5b92-2573-4981-a76c-bbd7756592c8"
HUB_RG="rg-mcaps-hub-dev"
DNS_RG="rg-mcaps-dns-dev"

# ── Discovered hub handles (verify with az; do not assume they never change) ──
HUB_VNET_ID="/subscriptions/${SUB}/resourceGroups/${HUB_RG}/providers/Microsoft.Network/virtualNetworks/vnet-mcaps-hub-dev"
ZONE_BLOB="/subscriptions/${SUB}/resourceGroups/${DNS_RG}/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
ZONE_KV="/subscriptions/${SUB}/resourceGroups/${DNS_RG}/providers/Microsoft.Network/privateDnsZones/privatelink.vaultcore.azure.net"
ZONE_ACR="/subscriptions/${SUB}/resourceGroups/${DNS_RG}/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io"

echo "Configuring azd env: $(azd env get-value AZURE_ENV_NAME 2>/dev/null || echo '<none>')"

# ── Region + zero-trust ──────────────────────────────────────────────────────
azd env set AZURE_LOCATION northcentralus
azd env set NETWORK_ISOLATION true

# ── Required bool flags (no defaults in params.json → must be set explicitly, or
#    azd passes "" and ARM rejects the bool params) ────────────────────────────
azd env set USE_UAI false                 # system-assigned identity (LZ default)
azd env set USE_CAPP_API_KEY false        # MI/Entra only, no API keys (SFI-005)
azd env set ENABLE_AGENTIC_RETRIEVAL false
azd env set USE_EXISTING_VNET false       # create the spoke VNet
azd env set DEPLOY_SUBNETS true           # ...and its subnets
azd env set SIDE_BY_SIDE true             # LZ default

# ── Keep every regional service in-region (no cross-region placement) ────────
azd env set AZURE_AI_FOUNDRY_LOCATION northcentralus
azd env set AZURE_COSMOS_LOCATION northcentralus
azd env set AZURE_SEARCH_LOCATION northcentralus
azd env set AZURE_SPEECH_LOCATION northcentralus
azd env set AZURE_PSQL_LOCATION northcentralus
azd env set AZURE_PE_LOCATION northcentralus

# ── Topology: spoke into existing hub (ailz-integrated) ──────────────────────
azd env set DEPLOYMENT_MODE ailz-integrated
azd env set HUB_INTEGRATION_HUB_VNET_RESOURCE_ID "$HUB_VNET_ID"
azd env set HUB_INTEGRATION_CREATE_HUB_PEERING true
# Reach the spoke over the hub P2S VPN: spoke uses the hub's remote gateway. The
# reverse hub->spoke peering + allowGatewayTransit is added post-provision
# (post-provision.sh) because it lives on the hub VNet, not this deployment.
azd env set HUB_INTEGRATION_PEERING_USE_REMOTE_GATEWAYS true

# ── Hub has NO firewall / NO NAT gateway → spoke owns compliant egress ───────
azd env set DEPLOY_AZURE_FIREWALL false
azd env set DEPLOY_NAT_GATEWAY true
# (leave HUB_INTEGRATION_EGRESS_NEXT_HOP_IP unset — no hub firewall to forward to)

# ── Hub uses P2S VPN + DNS resolver, NOT Bastion → no jumpbox/bastion ────────
azd env set DEPLOY_JUMPBOX false
azd env set DEPLOY_BASTION false

# ── Observability: spoke-local LAW ───────────────────────────────────────────
# Spoke (North Central US) is adjacent to the Central US hub on the US backbone, so
# cross-region log backhaul would be cheap — but we still let the LZ create a
# spoke-local LAW (clean per-demo lifecycle; deleted with the spoke) rather than
# reusing the shared hub LAW.
# (Intentionally leaving EXISTING_LOG_ANALYTICS_WORKSPACE_RESOURCE_ID unset.)

# ── Foundry + Agent Service (Search + Cosmos + Storage + KV) for hosted agents ─
azd env set DEPLOY_AAF_AGENT_SVC true
# AI Search: the REQUIRED Foundry Agent Service search (srch-aif-*, standard SKU,
# main.bicep:2998) deploys automatically with DEPLOY_AAF_AGENT_SVC and gates the
# hosted-agents capability host. North Central US has standard AI Search capacity
# (verified) AND is a supported Hosted Agents v2 region — unlike Central US (no
# hosted-agents support) and Sweden Central / East US 2 (AI Search capacity
# exhausted, ResourcesForSkuUnavailable). That combination is why this spoke lives
# in North Central US.
# The STANDALONE search (deploySearchService) is an OPTIONAL sample knowledge/
# retrieval component, cleanly skipped when disabled (main.bicep:2344). Left off to
# keep the deploy lean; set DEPLOY_SEARCH_SERVICE=true to add knowledge retrieval.
azd env set DEPLOY_SEARCH_SERVICE false
# (SKU for the optional standalone search if re-enabled; standard has capacity here.)
azd env set SEARCH_SERVICE_SKU standard

# ── Sample Container Apps workload: DISABLED ─────────────────────────────────
# troyhite's LZ ships a sample "orchestrator" Container App + Container Apps
# Environment (AKS-backed). It is NOT part of this demo's goal (private Foundry +
# Agent Service + AI Gateway for hosted agents) and its managed environment is
# subject to regional AKS-capacity shortages (hit AKSCapacityHeavyUsage in
# Sweden Central during the earlier attempt). Disable it so core Foundry
# infra provisions without the AKS dependency. Re-enable (set both true) if a
# Phase 2 scenario needs the sample app and regional capacity is available.
azd env set DEPLOY_CONTAINER_APPS false
azd env set DEPLOY_CONTAINER_ENV false

# ── Private ACR image builds inside the VNet (needed by Phase 2 azd up) ───────
# DISABLED for North Central US: Microsoft.ContainerRegistry/registries/agentPools
# is NOT available in northcentralus (ARM LocationNotAvailableForResourceType). The
# private Premium ACR still deploys; only the in-VNet build agent pool is skipped.
# Phase 2 image builds use an alternative (ACR cloud Quick Task, or an agent pool in
# an adjacent supported region). Re-enable only in a region that supports agentPools
# (eastus2, swedencentral, canadacentral, francecentral, switzerlandnorth, ...).
azd env set DEPLOY_ACR_TASK_AGENT_POOL false

# ── BYO ALL private DNS zones centrally from the hub (Path B, chosen) ─────────
# Run scripts/prep-hub-dns.sh FIRST — it creates any missing zones in rg-mcaps-dns-dev
# and VNet-links them to the hub so P2S VPN clients resolve the spoke's private
# endpoints. Every zone below is BYO'd so the spoke registers records into the
# hub-linked zone instead of creating an unreachable spoke-local zone.
Z="/subscriptions/${SUB}/resourceGroups/${DNS_RG}/providers/Microsoft.Network/privateDnsZones"
azd env set EXISTING_PRIVATE_DNS_ZONE_BLOB_RESOURCE_ID "$ZONE_BLOB"
azd env set EXISTING_PRIVATE_DNS_ZONE_KEYVAULT_RESOURCE_ID "$ZONE_KV"
azd env set EXISTING_PRIVATE_DNS_ZONE_ACR_RESOURCE_ID "$ZONE_ACR"
azd env set EXISTING_PRIVATE_DNS_ZONE_COGSVCS_RESOURCE_ID        "${Z}/privatelink.cognitiveservices.azure.com"
azd env set EXISTING_PRIVATE_DNS_ZONE_OPENAI_RESOURCE_ID         "${Z}/privatelink.openai.azure.com"
azd env set EXISTING_PRIVATE_DNS_ZONE_AISERVICES_RESOURCE_ID     "${Z}/privatelink.services.ai.azure.com"
azd env set EXISTING_PRIVATE_DNS_ZONE_SEARCH_RESOURCE_ID         "${Z}/privatelink.search.windows.net"
azd env set EXISTING_PRIVATE_DNS_ZONE_COSMOS_RESOURCE_ID         "${Z}/privatelink.documents.azure.com"
azd env set EXISTING_PRIVATE_DNS_ZONE_APPCONFIG_RESOURCE_ID      "${Z}/privatelink.azconfig.io"
azd env set EXISTING_PRIVATE_DNS_ZONE_CONTAINERAPPS_RESOURCE_ID  "${Z}/privatelink.azurecontainerapps.io"
azd env set EXISTING_PRIVATE_DNS_ZONE_AZUREMONITOR_RESOURCE_ID   "${Z}/privatelink.monitor.azure.com"
azd env set EXISTING_PRIVATE_DNS_ZONE_OMSOPSINSIGHTS_RESOURCE_ID "${Z}/privatelink.oms.opinsights.azure.com"
azd env set EXISTING_PRIVATE_DNS_ZONE_ODSOPSINSIGHTS_RESOURCE_ID "${Z}/privatelink.ods.opinsights.azure.com"
azd env set EXISTING_PRIVATE_DNS_ZONE_AZUREAUTOMATION_RESOURCE_ID "${Z}/privatelink.agentsvc.azure-automation.net"
azd env set EXISTING_PRIVATE_DNS_ZONE_APPINSIGHTS_RESOURCE_ID    "${Z}/privatelink.applicationinsights.azure.com"

echo "Done. Review with:  azd env get-values | sort"
