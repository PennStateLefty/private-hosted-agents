#!/usr/bin/env bash
# issue-tls-cert.sh — Issue a publicly-trusted TLS certificate for the App Gateway HTTPS
# listener via a FREE ACME CA (Let's Encrypt) using DNS-01 validation against the Azure
# DNS zone you control, then import it into Key Vault so the App Gateway can consume it.
#
# DEPLOY-GATED: only runs when PUBLIC_INGRESS_ENABLED=true — it participates in the
# sanctioned public-ingress exception (ADR-001).
#
# Why ACME + Azure DNS: the listener host (teams-bot.gutherie-demos.com) lives in an Azure
# public DNS zone, so DNS-01 domain-control validation is fully automatable and $0. The
# resulting cert is a normal publicly-trusted cert the Bot Channel Adapter will accept.
#
# Auth model: acme.sh's dns_azure hook is driven by a short-lived ARM bearer token minted
# from the CURRENT az login (AZUREDNS_BEARERTOKEN) — no service principal or client secret
# is created or stored (SFI-005). The caller must already hold DNS Zone Contributor on the
# zone and Key Vault Certificates Officer on the vault.
#
# Prereqs at runtime:
#   * az login to sub 987a5b92-... (control plane).
#   * Key Vault data-plane reachable: kv-zliorc-pha-dev-ncus-0 is PNA-disabled, so the
#     import step needs the P2S VPN connected + GSA Private Access disabled.
#   * openssl available (for PKCS12 packaging).
#
# References:
#   https://learn.microsoft.com/azure/application-gateway/key-vault-certs
#   https://github.com/acmesh-official/acme.sh/wiki/How-to-use-Azure-DNS
set -euo pipefail

if [[ "${PUBLIC_INGRESS_ENABLED:-false}" != "true" ]]; then
  echo "REFUSING: PUBLIC_INGRESS_ENABLED != true. This certificate is part of the sanctioned" >&2
  echo "public-ingress exception (ADR-001). Set PUBLIC_INGRESS_ENABLED=true to proceed." >&2
  exit 2
fi

# ---- inputs -----------------------------------------------------------------
CERT_HOSTNAME="${CERT_HOSTNAME:-teams-bot.gutherie-demos.com}"
DNS_ZONE="${DNS_ZONE:-gutherie-demos.com}"
DNS_ZONE_RG="${DNS_ZONE_RG:-rg-mcaps-dns-dev}"
KEYVAULT="${KEYVAULT:-kv-zliorc-pha-dev-ncus-0}"
KV_CERT_NAME="${KV_CERT_NAME:-teams-bot-listener}"
ACME_EMAIL="${ACME_EMAIL:?set ACME_EMAIL to a contact address for the ACME account}"
# Use Let's Encrypt production by default; set ACME_SERVER=letsencrypt_test to stage.
ACME_SERVER="${ACME_SERVER:-letsencrypt}"
ACME_HOME="${ACME_HOME:-$HOME/.acme.sh}"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

SUB_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"

echo "==> Cert:      ${CERT_HOSTNAME}"
echo "==> DNS zone:  ${DNS_ZONE} (rg ${DNS_ZONE_RG})"
echo "==> Key Vault: ${KEYVAULT} / cert ${KV_CERT_NAME}"
echo "==> ACME CA:   ${ACME_SERVER}"

# ---- 1/5 sanity: zone exists and caller can write to it ---------------------
echo "==> 1/5 Verify DNS zone access"
az network dns zone show -g "$DNS_ZONE_RG" -n "$DNS_ZONE" --query name -o tsv >/dev/null

# ---- 2/5 install acme.sh (local, no root) -----------------------------------
echo "==> 2/5 Ensure acme.sh present"
if [[ ! -x "${ACME_HOME}/acme.sh" ]]; then
  curl -fsSL https://get.acme.sh | sh -s email="$ACME_EMAIL" >/dev/null
fi
ACME="${ACME_HOME}/acme.sh"
"$ACME" --set-default-ca --server "$ACME_SERVER" >/dev/null

# ---- 3/5 issue via DNS-01 against Azure DNS ---------------------------------
echo "==> 3/5 Issue certificate (DNS-01 via Azure DNS)"
# Drive dns_azure with the current az session's ARM token — no service principal.
export AZUREDNS_SUBSCRIPTIONID="$SUB_ID"
export AZUREDNS_TENANTID="$TENANT_ID"
export AZUREDNS_BEARERTOKEN="$(az account get-access-token --resource https://management.azure.com --query accessToken -o tsv)"

set +e
"$ACME" --issue --dns dns_azure -d "$CERT_HOSTNAME" \
  --keylength 2048 --server "$ACME_SERVER"
rc=$?
set -e
# acme.sh returns 2 when the cert already exists and is not due for renewal — treat as success.
if [[ $rc -ne 0 && $rc -ne 2 ]]; then
  echo "ERROR: acme.sh issuance failed (rc=$rc). Check DNS Zone Contributor rights on ${DNS_ZONE}." >&2
  exit 1
fi

# ---- 4/5 package as PKCS12 --------------------------------------------------
echo "==> 4/5 Package cert as PKCS12"
CERT_DIR="${ACME_HOME}/${CERT_HOSTNAME}_ecc"
[[ -d "$CERT_DIR" ]] || CERT_DIR="${ACME_HOME}/${CERT_HOSTNAME}"
PFX="${WORKDIR}/${KV_CERT_NAME}.pfx"
# Empty PFX password: Key Vault import accepts a password-less PFX and App Gateway reads it
# through the vault reference, so no secret is persisted anywhere.
openssl pkcs12 -export \
  -inkey "${CERT_DIR}/${CERT_HOSTNAME}.key" \
  -in "${CERT_DIR}/${CERT_HOSTNAME}.cer" \
  -certfile "${CERT_DIR}/ca.cer" \
  -passout pass: \
  -out "$PFX"

# ---- 5/5 import into Key Vault ----------------------------------------------
echo "==> 5/5 Import into Key Vault (needs private data-plane: VPN + GSA off)"
az keyvault certificate import \
  --vault-name "$KEYVAULT" -n "$KV_CERT_NAME" \
  -f "$PFX" --password "" -o none

# The App Gateway sslCertificate.keyVaultSecretId must be the UNVERSIONED secret id so the
# gateway auto-picks up renewals. For a KV certificate, the sibling secret holds the PFX.
SECRET_ID_UNVERSIONED="https://${KEYVAULT}.vault.azure.net/secrets/${KV_CERT_NAME}"
echo
echo "TLS cert imported. Wire this into the App Gateway deploy:"
echo "  sslCertKeyVaultSecretId = ${SECRET_ID_UNVERSIONED}"
echo "  listenerHostName        = ${CERT_HOSTNAME}"
echo
echo "Reminder: grant the App Gateway user-assigned identity 'Key Vault Secrets User' on ${KEYVAULT}."
