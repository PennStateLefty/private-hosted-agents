#!/usr/bin/env bash
# harden-gateway-inbound.sh — make the APIM AI gateway inbound fully private.
#
# After the governance proof (scripts/gateway-proof.py) the gateway is reachable on
# its public hostname. This script closes that: it adds an inbound PRIVATE ENDPOINT
# for the APIM gateway into the spoke, wires it to the BYO privatelink.azure-api.net
# zone (hub-linked, so P2S VPN clients resolve it), links the zone to the spoke, and
# sets publicNetworkAccess=false. Result: the gateway is callable only over the private
# network (VPN), exactly like the Foundry endpoint.
#
# Idempotent: safe to re-run.
set -euo pipefail

SUB="${SUB:-987a5b92-2573-4981-a76c-bbd7756592c8}"
RG="${RG:-rg-pha-dev}"
APIM="${APIM:-apim-pha-dev}"
VNET="${VNET:-vnet-zliorc-pha-dev-ncus-001}"
PE_SUBNET="${PE_SUBNET:-pe-subnet}"
DNS_RG="${DNS_RG:-rg-mcaps-dns-dev}"
ZONE="${ZONE:-privatelink.azure-api.net}"
PE_NAME="${PE_NAME:-pe-apim-pha-dev}"

APIM_ID="$(az apim show -g "$RG" -n "$APIM" --query id -o tsv)"
SUBNET_ID="/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworks/$VNET/subnets/$PE_SUBNET"
ZONE_ID="/subscriptions/$SUB/resourceGroups/$DNS_RG/providers/Microsoft.Network/privateDnsZones/$ZONE"

echo "==> 1/4 discover APIM private-link group id"
GROUP="$(az network private-link-resource list --id "$APIM_ID" --query "[0].groupId" -o tsv 2>/dev/null || echo Gateway)"
GROUP="${GROUP:-Gateway}"
echo "    group: $GROUP"

echo "==> 2/4 create/ensure private endpoint $PE_NAME in $PE_SUBNET"
if ! az network private-endpoint show -g "$RG" -n "$PE_NAME" >/dev/null 2>&1; then
  # NOTE: pass the FULL subnet resource id via --subnet (do NOT use --vnet-name +
  # short subnet name: the CLI uppercases the RG/VNet in the internal reference and
  # fails with InvalidResourceReference). Also pin -l to the spoke region.
  az network private-endpoint create -g "$RG" -n "$PE_NAME" -l northcentralus \
    --subnet "$SUBNET_ID" \
    --private-connection-resource-id "$APIM_ID" --group-id "$GROUP" \
    --connection-name "conn-apim" -o none
fi

echo "==> 3/4 wire PE DNS zone group + link zone to spoke"
az network private-endpoint dns-zone-group create -g "$RG" \
  --endpoint-name "$PE_NAME" --name "default" \
  --private-dns-zone "$ZONE_ID" --zone-name "$ZONE" -o none 2>/dev/null || true
# Link the BYO zone to the spoke (hub link already exists for VPN clients).
az network private-dns link vnet create -g "$DNS_RG" -z "$ZONE" \
  -n "link-${VNET}" -v "/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworks/$VNET" \
  -e false -o none 2>/dev/null || true

echo "==> 4/4 disable public network access on the gateway"
# StandardV2 rejects PNA changes on the api-version the `az apim update` CLI uses
# (OperationSupportedInSkuForApiVersions). PATCH via ARM REST with a supported version.
az rest --method patch \
  --url "https://management.azure.com${APIM_ID}?api-version=2024-06-01-preview" \
  --body '{"properties":{"publicNetworkAccess":"Disabled"}}' -o none

echo "done. gateway inbound is now private; resolve $APIM.azure-api.net over the VPN."
az apim show -g "$RG" -n "$APIM" --query "{pna:publicNetworkAccess, vnet:virtualNetworkType}" -o json
