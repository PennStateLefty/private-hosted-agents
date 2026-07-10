# PROVISION.md — Phase 1: private Foundry landing zone + APIM AI Gateway

Deploys a **private-networked Azure AI Foundry + Agent Service** as a spoke into the
existing **`mcaps-foundation` hub**, then (optionally) an **APIM GenAI gateway** in front
of it. Scope is a **non-production compliance/network simulation** — enough to enforce the
MCAPS controls and reproduce the private-network restrictions a customer faces. Single hub
(Central US); this spoke is deployed in **North Central US** (US-adjacent to the hub).

> **Status: DEPLOYED.** Phase 1 is provisioned and validated in `rg-pha-dev` (North Central US,
> resource token `zliorc3ajydko`). Deployed handles for the Phase 2 hand-off are in
> [`docs/PHASE1-HANDOFF.md`](docs/PHASE1-HANDOFF.md). This runbook reproduces the deployment
> from scratch and is idempotent (safe to re-run).

## Topology (what gets built)

```
  ┌─ rg-mcaps-hub-dev (Central US) ─────── EXISTING ─────────────┐
  │  vnet-mcaps-hub-dev 10.0.0.0/16                              │
  │  P2S VPN gateway (Entra) · DNS Private Resolver 10.0.1.4     │
  └───────────────▲─────────────────────────────┬───────────────┘
      global peering │ (gateway transit)         │ hub→spoke peering (post-provision)
  ┌───────────────┴─────────────────────────────▼───────────────┐
  │  spoke rg (North Central US) 192.168.0.0/21 (LZ-assigned)                 │
  │  Foundry account+project (PNA Disabled, MI, PE)             │
  │  Agent Service: Search + Cosmos + Storage + Key Vault (PE)  │
  │  spoke-local ACR (Premium, PE) — NO ACR Task pool (NCUS n/a) │
  │  spoke-local Log Analytics (regional — no backhaul)         │
  │  NAT gateway (compliant egress) · APIM GenAI gateway        │
  └─────────────────────────────────────────────────────────────┘
```

**Cross-region traffic is deliberately minimized:** all data-heavy services (agent
Cosmos/Search/Storage/KV, ACR, Foundry inference, Log Analytics) are in North Central US.
Only DNS queries + low-volume P2S admin access backhaul to the Central US hub.

## Prerequisites

- `azd` ≥ 1.27, `az` ≥ 2.88, `bicep` ≥ 0.44 (all present on this machine).
- Contributor + private-DNS + network-peering rights in subscription
  `987a5b92-2573-4981-a76c-bbd7756592c8`.
- Connected to the hub **P2S VPN** for post-deploy validation.

## Step 1 — (optional, recommended) pre-create + hub-link the missing DNS zones

A private Foundry/AI + APIM needs privatelink zones the hub doesn't have yet. Pre-creating
them centrally and linking to the hub VNet means **P2S VPN clients can resolve** the private
endpoints. Prints BYO resource IDs to paste into Step 2.

```bash
./scripts/prep-hub-dns.sh
```

(Alternative: skip this and let the spoke create the zones, then run `post-provision.sh`
to hub-link them — see Step 5.)

## Step 2 — create + configure the azd environment

```bash
cd landing-zone
azd auth login
azd env new pha-dev --subscription 987a5b92-2573-4981-a76c-bbd7756592c8 --location northcentralus
../scripts/configure-azd-env.sh          # sets every env var for this hub (see script)
# If you ran Step 1, also paste the printed EXISTING_PRIVATE_DNS_ZONE_*_RESOURCE_ID lines.
azd env get-values | sort                 # review
```

Key decisions baked into `configure-azd-env.sh`:
`DEPLOYMENT_MODE=ailz-integrated`, `NETWORK_ISOLATION=true`, hub VNet peering with
`USE_REMOTE_GATEWAYS=true`, `DEPLOY_NAT_GATEWAY=true` (hub has no firewall/NAT),
`DEPLOY_BASTION/JUMPBOX=false` (reach via VPN), `DEPLOY_AAF_AGENT_SVC=true`,
`DEPLOY_ACR_TASK_AGENT_POOL=false` (agentPools unavailable in North Central US — the private
ACR still deploys), spoke-local LAW (regional), BYO the 3 hub zones that
already exist. Chat model set to **gpt-5.4-mini `GlobalStandard`** (pay-go, POLICY-006: no PTU;
gpt-4o is retiring and the control plane denies it) in
`landing-zone/main.parameters.json`.

## Step 3 — preflight + what-if (read-only)

```bash
azd provision --preview          # what-if; the LZ preprovision hook also checks CIDR/quota/BYO IDs
```

Fix any preflight findings (CIDR overlap, model quota, missing BYO IDs)
before proceeding. To bypass the hook only if it misfires: `azd env set PREFLIGHT_SKIP true`.

## Step 4 — provision the landing zone (~37 min, ~80 resources)

```bash
azd provision
```

> **Region — North Central US (required for Hosted Agents v2).** This spoke first targeted
> Sweden Central (out of AI Search `standard` capacity, `ResourcesForSkuUnavailable`), then
> Central US — but **Hosted Agents v2 is not available in Central US**
> ([regions list](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents#limits-pricing-and-availability)).
> The supported-regions list was cross-checked against AI Search capacity (East US 2 + Sweden
> Central exhausted) and model quota (subscription-global) → **North Central US** is the verified
> fit (hosted-agents v2 + Invocations-WebSocket preview + Search capacity). The private Foundry
> **Agent Service** standard setup hard-requires an **Azure AI Search** (`srch-aif-*`, SKU
> `standard`, `main.bicep:2998`). To relocate, pick another region that supports **both**
> hosted-agents **and** agentPools if you want in-VNet ACR builds — e.g. eastus2, canadacentral,
> swedencentral, francecentral, switzerlandnorth — re-verify quota + Search capacity, update the
> region vars in `scripts/configure-azd-env.sh` + `landing-zone/main.parameters.json`, re-provision.
>
> `text-embedding-3-large` is deployed as **GlobalStandard** (subscription-global quota).
> If a fresh region returns `ResourcesForSkuUnavailable` on `srch-aif-`, wait + re-run
> `azd provision` (idempotent; succeeded resources are skipped) or relocate as above.

## Step 5 — post-provision wiring (VPN reach + DNS)

Adds the reverse hub→spoke peering **with gateway transit** (so P2S clients route into the
spoke), hub-links any spoke-created privatelink zones, **and links the BYO hub privatelink
zones to the spoke VNet** (so in-spoke resources — the Foundry Agent Service containers in
`agent-subnet` — can resolve Cosmos/Search/Storage/Foundry). Pass the spoke RG **and the spoke
VNet name** (the RG may contain more than one VNet — always name the current spoke VNet
explicitly so the script doesn't peer the wrong one):

```bash
./scripts/post-provision.sh <spoke-rg> <spoke-vnet>   # e.g. rg-pha-dev vnet-zliorc-pha-dev-ncus-001
```

## Step 6 — (optional) deploy the APIM AI Gateway

APIM is additive and slow/costly (~45 min). Populate `infra/main.bicepparam` from the LZ
outputs (`cd landing-zone && azd env get-values`), then:

```bash
az deployment sub create -l northcentralus -f infra/main.bicep -p infra/main.bicepparam
```

**Known compliance gap to close (SFI-012):** AVM `api-management/service` 0.9.1 exposes
neither `publicNetworkAccess` nor `privateEndpoints`. It deploys StandardV2 with optional
VNet integration; **disable public inbound after deploy**:

```bash
az apim update -g <spoke-rg> -n apim-pha-dev --public-network-access false
```

Then import your Azure OpenAI OpenAPI as an API named `azure-openai` and attach the GenAI
policy emitted by the module output `aoaiApiPolicyXml` (managed-identity auth to Foundry +
per-key token-limit + token metrics).

## Step 7 — validate over the P2S VPN

```bash
nslookup aif-zliorc-pha-dev-ncus-001.openai.azure.com   # expect 192.168.2.30 (spoke private IP)
# then a private inference call from a VPN-connected client
```

> **macOS + Global Secure Access (GSA) gotcha:** if the machine runs the GSA client, its
> **Private Access** profile transparently intercepts RFC1918 flows *above* the route table —
> TCP appears to connect but TLS blackholes (~5 s) and `tcpdump -i utun<vpn>` shows nothing.
> Fix: **disable GSA Private Access** (leave Internet Access + M365 on) **and** keep the Azure
> P2S VPN connected (toggling GSA can drop the tunnel — reconnect with
> `scutil --nc start "vnet-mcaps-hub-dev"`). macOS scoped DNS also sends `*.openai.azure.com`
> to the public resolver, so pin the private IP for a direct test:
> `curl --resolve <acct>.openai.azure.com:443:192.168.2.30 ...`.

> **"Error loading your agents" in the Foundry portal** = the Agent Service backend can't
> resolve its **CosmosDB** (or Search/Storage) private endpoint. Cause: the `privatelink.*`
> zones weren't linked to the **spoke** VNet (only the hub). Step 5's post-provision script now
> links them to the spoke; if you see this error, re-run `post-provision.sh` or link the six
> zones (`documents`, `search`, `blob`, `openai`, `cognitiveservices`, `services.ai`) in
> `rg-mcaps-dns-dev` to the spoke VNet.

## Compliance notes (MCAPS)

| Control | How it's met |
| --- | --- |
| SFI-012 private endpoints + PNA Disabled | LZ sets PNA Disabled + PE on all PaaS. **APIM: close manually (Step 6).** |
| SFI-013 no default outbound | Spoke subnets `defaultOutboundAccess:false`; NAT gateway for egress |
| SFI-005 MI only | Foundry/ACR/APIM→Foundry all managed-identity; no keys/secrets |
| POLICY-006 Foundry Standard only | Models on pay-go `GlobalStandard` (no PTU/ProvisionedManaged) |
| POLICY-013 disableLocalAuth | Foundry account `disableLocalAuth:true`; **AI Search `srch-aif` remediated to Entra-only** (`disableLocalAuth:true`, `authOptions:null`) live + in `main.bicep`. Project MI holds Search Service/Index Data Contributor. |
| Idempotent | `azd provision` + post-provision scripts re-run cleanly |

## Teardown

```bash
cd landing-zone && azd down --purge
# then remove the reverse hub peering + any hub DNS links added by the scripts.
```

> **⚠ Teardown caveat — Container Apps SAL can block VNet deletion.** If the LZ's Container
> Apps environment was ever provisioned against `agent-subnet` (delegated
> `Microsoft.App/environments`), a `serviceAssociationLink` can be left behind that makes the
> spoke VNet **undeletable** (`InUseSubnetCannotBeDeleted`), silently stalling `azd down` /
> `az group delete`. If the backing managed environment lives in a **Microsoft-managed
> subscription** (RG name like `hobov3_*`), you cannot clear it yourself — **open a support
> ticket**. In this deployment `DEPLOY_CONTAINER_APPS=false`, so a fresh spoke avoids it; the
> current `rg-pha-dev` still carries such an orphan from an earlier Central US attempt
> (`vnet-vf2fib-pha-dev-cus-001`), pending a support ticket.
