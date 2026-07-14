#!/usr/bin/env bash
# create-appgw-subnet.sh — Create the dedicated Application Gateway v2 subnet + NSG in the
# spoke, locked down to the traffic App Gateway v2 requires plus the Teams Bot Channel
# Adapter source ranges. DEPLOY-GATED: only runs when PUBLIC_INGRESS_ENABLED=true because
# it participates in the sanctioned public-ingress exception (ADR-001).
#
# App Gateway v2 needs its own subnet (/26 or larger, no other resources). The NSG MUST
# allow inbound GatewayManager (65200-65535) and AzureLoadBalancer, or the gateway fails to
# provision. Inbound 443 is restricted to the Teams "Bot Channel Adapter" IP ranges — fetch
# the current list from the Microsoft 365 URLs & IP ranges feed (id 9, "Teams") and pass it
# in TEAMS_BOT_ADAPTER_RANGES (comma-separated). See:
#   https://learn.microsoft.com/microsoft-365/enterprise/urls-and-ip-address-ranges
set -euo pipefail

if [[ "${PUBLIC_INGRESS_ENABLED:-false}" != "true" ]]; then
  echo "REFUSING: PUBLIC_INGRESS_ENABLED != true. This subnet is part of the sanctioned" >&2
  echo "public-ingress exception (ADR-001). Set PUBLIC_INGRESS_ENABLED=true to proceed." >&2
  exit 2
fi

RG="${AZURE_RESOURCE_GROUP:-rg-pha-dev}"
LOCATION="${AZURE_LOCATION:-northcentralus}"
VNET="${SPOKE_VNET:-vnet-zliorc-pha-dev-ncus-001}"
SUBNET="${APPGW_SUBNET:-appgw-subnet}"
SUBNET_PREFIX="${APPGW_SUBNET_PREFIX:?set APPGW_SUBNET_PREFIX to a free /26 in the spoke, e.g. 192.168.5.0/26}"
NSG="${APPGW_NSG:-appgw-nsg}"
# Comma-separated CIDRs for the Teams Bot Channel Adapter inbound to 443. REQUIRED (fail-
# closed): we do NOT fall back to the broad AzureCloud service tag. Fetch the current ranges
# from the Microsoft 365 URLs & IP feed (id 9, "Teams") / Azure Bot Service egress and pass
# them here. Set TEAMS_BOT_ADAPTER_RANGES=AzureCloud explicitly to accept the broad tag.
TEAMS_BOT_ADAPTER_RANGES="${TEAMS_BOT_ADAPTER_RANGES:?set TEAMS_BOT_ADAPTER_RANGES to the Teams/Bot Channel Adapter CIDRs (comma-separated); use =AzureCloud to intentionally accept the broad service tag}"

echo "==> 1/3 Create NSG ${NSG}"
az network nsg create -g "$RG" -n "$NSG" -l "$LOCATION" -o none

echo "==> 2/3 NSG rules (GatewayManager + LB + Teams 443 + explicit Internet deny)"
az network nsg rule create -g "$RG" --nsg-name "$NSG" -n Allow-GatewayManager \
  --priority 100 --direction Inbound --access Allow --protocol Tcp \
  --source-address-prefixes GatewayManager --destination-port-ranges 65200-65535 -o none
az network nsg rule create -g "$RG" --nsg-name "$NSG" -n Allow-AzureLoadBalancer \
  --priority 110 --direction Inbound --access Allow --protocol Tcp \
  --source-address-prefixes AzureLoadBalancer --destination-port-ranges '*' -o none
# shellcheck disable=SC2206
RANGES=(${TEAMS_BOT_ADAPTER_RANGES//,/ })
az network nsg rule create -g "$RG" --nsg-name "$NSG" -n Allow-Teams-Https \
  --priority 200 --direction Inbound --access Allow --protocol Tcp \
  --source-address-prefixes "${RANGES[@]}" --destination-port-ranges 443 -o none
# Explicit defense-in-depth deny of all other Internet inbound (below the default 65500 deny
# but above nothing else; makes the posture auditable rather than implicit).
az network nsg rule create -g "$RG" --nsg-name "$NSG" -n DenyAllInternetInbound \
  --priority 4096 --direction Inbound --access Deny --protocol '*' \
  --source-address-prefixes Internet --destination-port-ranges '*' -o none

echo "==> 3/3 Create subnet ${SUBNET} (${SUBNET_PREFIX}) with defaultOutboundAccess=false"
az network vnet subnet create -g "$RG" --vnet-name "$VNET" -n "$SUBNET" \
  --address-prefixes "$SUBNET_PREFIX" \
  --network-security-group "$NSG" \
  --default-outbound-access false -o none

SUBNET_ID="$(az network vnet subnet show -g "$RG" --vnet-name "$VNET" -n "$SUBNET" --query id -o tsv)"
echo "APPGW subnet id: ${SUBNET_ID}"
