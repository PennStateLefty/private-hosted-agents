# G7 — APIM AI Gateway governance — PASS

Proves an **Azure API Management GenAI (AI) gateway** sits in front of the private
Foundry account and **governs** model traffic: it enforces a token-per-minute budget
(HTTP **429** when the estimated request exceeds the budget) and, when the budget is
restored, lets governed traffic through to a **200** completion — authenticating to the
private backend with a **managed identity (no keys)** over **VNet-integrated** egress.
Proven **3 consecutive times**.

## Deployed gateway (live)

| Property | Value |
| --- | --- |
| Service | `apim-pha-dev` (StandardV2) |
| Gateway URL | `https://apim-pha-dev.azure-api.net` |
| VNet integration | `virtualNetworkType=External`, subnet `apim-subnet` (192.168.4.0/27, delegated `Microsoft.Web/serverFarms`, NSG `nsg-apim-pha-dev`) |
| Inbound access | **Private only** — `publicNetworkAccess=Disabled`; private endpoint `pe-apim-pha-dev` (conn `conn-apim`, **Approved**) in `pe-subnet` → resolves to **192.168.2.26** via BYO `privatelink.azure-api.net` (hub- + spoke-linked) |
| Auth to Foundry | System-assigned MI `38157d71-…` granted `Cognitive Services OpenAI User` — **no subscription/API keys** (policy `authentication-managed-identity`) |
| Backend | private Foundry `aif-zliorc-pha-dev-ncus-001.openai.azure.com` → resolves to **192.168.2.30** (spoke-linked `privatelink.openai.azure.com`) |
| Governance policy | `azure-openai-token-limit` (estimate-prompt-tokens) + `azure-openai-emit-token-metric` (namespace `genai`) |

IaC: `infra/main.bicep` + `infra/modules/ai-gateway.bicep` (AVM `avm/res/api-management/service:0.9.1`, pinned), deployed with `az deployment sub create`. Adapted for this landing zone: `virtualNetworkType=External` (StandardV2 outbound integration) and optional UAMI (`USE_UAI=false` → system-assigned only).

## Proof — `scripts/gateway-proof.py` (3 consecutive runs)

Each run flips the gateway policy and calls the real gateway endpoint **over the private
path** (`publicNetworkAccess=Disabled`; the harness pins the connection to the private
endpoint IP `192.168.2.26` with SNI/Host preserved, since the macOS resolver may still
return the public A record to the socket layer):

```
run1: ENFORCE tpm=100 -> HTTP 429 (remaining=100) | RESTORE tpm=20000 -> HTTP 200 completion='Hello there, friend.'  | PASS
run2: ENFORCE tpm=100 -> HTTP 429 (remaining=100) | RESTORE tpm=20000 -> HTTP 200 completion='Hello, world, friend'  | PASS
run3: ENFORCE tpm=100 -> HTTP 429 (remaining=100) | RESTORE tpm=20000 -> HTTP 200 completion='Hello there, friend.'  | PASS

G7 governance: 3/3 consecutive PASS (end state: tpm=20000)
```

- **Enforce**: a large prompt against a low budget returns `429` with
  `Retry-After: 60`, `x-ratelimit-remaining-tokens: 100`, and body
  *"Token limit will exceed based on estimated request tokens."*
- **Restore**: a small prompt against the sane budget returns `200` with a real model
  completion — the backend was reached **privately** and authenticated via managed
  identity (backend AOAI rate-limit headers, e.g. `x-ratelimit-remaining-tokens: 19979`,
  are passed through). No keys anywhere in the path.

Raw per-run evidence: `evidence/g7-gateway-run{1,2,3}.json`. End state leaves the
production-sane budget (`tokens-per-minute=20000`) in place.

## MCAPS posture

- **Managed-identity only** to the backend — no Foundry keys, no APIM subscription key
  on the backend hop (the inbound subscription key only authenticates the *caller* to
  the gateway and keys the per-tenant token counter).
- **Private egress** to Foundry via VNet integration + spoke `privatelink.openai.azure.com`.
- **Approved region** northcentralus; **idempotent** (re-`az deployment sub create`).
- **Inbound fully private (hardening complete):** `publicNetworkAccess=Disabled`; the
  gateway is reachable only through its inbound **private endpoint** `pe-apim-pha-dev`
  (connection **Approved**) wired to the BYO `privatelink.azure-api.net` zone (hub-linked
  for P2S VPN clients + spoke-linked), resolving `apim-pha-dev.azure-api.net` → 192.168.2.26.
  Public callers now get HTTP 403 *"public network access ... is disabled ... use the
  Private Endpoint"*. Applied by `scripts/harden-gateway-inbound.sh`; governance re-proven
  3/3 over this private path (above).

## Reproduce

```
cd workshop-concierge-adk
# Private path (default): pins the APIM private-endpoint IP, requires the P2S VPN.
python3 scripts/gateway-proof.py            # 3/3 PASS, restores tpm=20000
# From inside the VNet with working private DNS, unset the pin:
APIM_PRIVATE_IP= python3 scripts/gateway-proof.py
```
