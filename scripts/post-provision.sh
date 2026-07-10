#!/usr/bin/env bash
# post-provision.sh — run AFTER `azd provision` succeeds.
# 1) Adds the reverse hub->spoke VNet peering WITH gateway transit so P2S VPN
#    clients on the hub can route into the spoke (the spoke side already set
#    useRemoteGateways=true).
# 2) Links every spoke-created privatelink DNS zone to the hub VNet so VPN
#    clients (resolving via hub resolver 10.0.1.4) get the private A records.
#    (Skip this step for any zone you supplied as BYO in the hub — already linked.)
# 3) Links the BYO hub privatelink DNS zones to the SPOKE VNet so resources
#    running INSIDE the spoke (e.g. the Foundry Agent Service containers in
#    agent-subnet) can resolve Cosmos/Search/Storage/Foundry private endpoints.
#    The spoke uses Azure-default DNS (168.63.129.16), which only sees zones
#    linked to the spoke itself — without this the portal throws
#    "Error loading your agents" because the backend can't resolve CosmosDB.
#
# Idempotent. Pass the spoke resource group + spoke VNet name, or let it discover
# them from `azd env get-values`.
set -euo pipefail

SUB="987a5b92-2573-4981-a76c-bbd7756592c8"
HUB_RG="rg-mcaps-hub-dev"
HUB_VNET="vnet-mcaps-hub-dev"
HUB_VNET_ID="/subscriptions/${SUB}/resourceGroups/${HUB_RG}/providers/Microsoft.Network/virtualNetworks/${HUB_VNET}"
# Shared/BYO private DNS zones live here in this landing zone.
DNS_RG="rg-mcaps-dns-dev"

SPOKE_RG="${1:-$(azd env get-value AZURE_RESOURCE_GROUP 2>/dev/null || true)}"
SPOKE_VNET="${2:-}"

az account set --subscription "$SUB"

if [[ -z "$SPOKE_RG" ]]; then
  echo "ERROR: pass SPOKE_RG as arg 1 (e.g. ./post-provision.sh rg-pha-dev vnet-pha-dev)"; exit 1
fi
if [[ -z "$SPOKE_VNET" ]]; then
  SPOKE_VNET="$(az network vnet list -g "$SPOKE_RG" --query "[0].name" -o tsv)"
fi
SPOKE_VNET_ID="$(az network vnet show -g "$SPOKE_RG" -n "$SPOKE_VNET" --query id -o tsv)"

echo "==> Reverse peering ${HUB_VNET} -> ${SPOKE_VNET} (allow gateway transit)"
az network vnet peering create \
  -g "$HUB_RG" --vnet-name "$HUB_VNET" -n "peer-hub-to-${SPOKE_VNET}" \
  --remote-vnet "$SPOKE_VNET_ID" \
  --allow-vnet-access --allow-forwarded-traffic --allow-gateway-transit -o none
echo "    done."

echo "==> Linking spoke-created privatelink DNS zones to the hub VNet"
# Zones the spoke created live in the spoke RG; BYO zones are already hub-linked.
for zone in $(az network private-dns zone list -g "$SPOKE_RG" --query "[?starts_with(name,'privatelink')].name" -o tsv); do
  echo "    link-hub -> ${zone}"
  az network private-dns link vnet create -g "$SPOKE_RG" -z "$zone" \
    -n "link-hub" --virtual-network "$HUB_VNET_ID" --registration-enabled false -o none 2>/dev/null || true
done

echo "==> Linking BYO hub privatelink DNS zones to the SPOKE VNet"
# Without this, in-spoke resources (Foundry Agent Service containers) resolve via
# Azure-default DNS and cannot see the hub-only zones -> "Error loading your agents"
# (CosmosDB/Search/Storage resolution failure). Link name is derived from the
# spoke VNet so it is unique per zone and idempotent.
for zone in $(az network private-dns zone list -g "$DNS_RG" --query "[?starts_with(name,'privatelink')].name" -o tsv); do
  echo "    link-spoke (${SPOKE_VNET}) -> ${zone}"
  az network private-dns link vnet create -g "$DNS_RG" -z "$zone" \
    -n "link-${SPOKE_VNET}" --virtual-network "$SPOKE_VNET_ID" --registration-enabled false -o none 2>/dev/null || true
done

echo "All done. Validate:"
echo "  - from a P2S VPN client:  nslookup <foundry-account>.openai.azure.com  (expect a 192.168.2.x private IP)"
echo "  - in the Foundry portal:  open the Agents blade (should load without a CosmosDB resolution error)"
