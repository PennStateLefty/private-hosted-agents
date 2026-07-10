# Phase 1 → Phase 2 handoff — deployed private Foundry environment

Phase 1 (private-networked Microsoft Foundry + Agent Service, MCAPS-compliant) is
**deployed and validated**. This document records the live handles Phase 2 (the C#
Foundry **hosted agents**) needs. Do **not** hardcode these into IaC — they are captured
here for developer convenience; the authoritative source is `azd env get-values` /
Azure MCP discovery.

## Deployment facts

| Item | Value |
| --- | --- |
| Subscription | `987a5b92-2573-4981-a76c-bbd7756592c8` (`ME-MngEnvMCAP438243-jgutherie-1`) |
| Resource group | `rg-pha-dev` |
| Region | **North Central US** |
| Resource token | `zliorc3ajydko` (short: `zliorc`) |
| Spoke VNet | `vnet-zliorc-pha-dev-ncus-001` — address space **`192.168.0.0/21`** |
| Peering | spoke↔hub `Connected` both directions (global peering + gateway transit) |

> **Region note — why North Central US.** The stack was first deployed to **Central US**,
> but **Hosted Agents v2 is not available in Central US**
> ([regions list](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents#limits-pricing-and-availability)).
> Candidate regions were cross-checked against **AI Search `standard` capacity**: Sweden
> Central and East US 2 were **exhausted** (`InsufficientResourcesAvailable`); **North
> Central US** was verified available and also carries the Invocations-WebSocket preview.
> Model quota (`gpt-5.4-mini` + `text-embedding-3-large`, GlobalStandard) is subscription-
> global, so no per-region quota move was needed. NCUS is US-adjacent to the Central US hub
> (backbone hop, not trans-Atlantic).

## Foundry handles (Phase 2 targets)

| Handle | Value |
| --- | --- |
| **Project endpoint** (SDK) | `https://aif-zliorc-pha-dev-ncus-001.services.ai.azure.com/api/projects/aifp-zliorc-pha-dev-ncus-001` |
| Account endpoint | `https://aif-zliorc-pha-dev-ncus-001.cognitiveservices.azure.com/` |
| Foundry account | `aif-zliorc-pha-dev-ncus-001` (PNA **Disabled**, `disableLocalAuth: true`, SystemAssigned MI) |
| Foundry project | `aifp-zliorc-pha-dev-ncus-001` |
| Account MI principalId | `6cc9da6a-657d-4094-a291-42bec57689e5` |
| Project MI principalId | `81cc09d9-3059-4c21-9616-78d815d0c82e` |
| Capability host (hosted-agents runtime) | `chagentaifpzliorcphadevncus001` — **Succeeded** |

### Model deployments (pay-go, no PTU — POLICY-006)

| Deployment name | Model | SKU | Capacity |
| --- | --- | --- | --- |
| `chat` | `gpt-5.4-mini` | GlobalStandard | 40 |
| `text-embedding` | `text-embedding-3-large` | GlobalStandard | 10 |

> `text-embedding-3-large` is deployed as **GlobalStandard** (subscription-global quota) —
> keep it GlobalStandard; do not switch the embedding SKU back to regional `Standard`.

## Agent Service backing stores (all private endpoint, Entra-only)

| Resource | Name | Auth |
| --- | --- | --- |
| AI Search | `srch-aif-zliorc-pha-dev-ncus-001` | **Entra-only** (`disableLocalAuth: true`, `authOptions: null`, PNA Disabled) |
| Cosmos DB | `cosmos-aif-zliorc-pha-dev-ncus-001` | AAD |
| Storage | `staifzliorcphadevncus001` / `stzliorcphadevncus001` | AAD |
| Key Vault | `kv-zliorc-pha-dev-ncus-0` / `kv-ai-zliorc3ajydko` | Entra + RBAC |
| Container Registry | `crzliorcphadevncus001.azurecr.io` | Entra (admin disabled), PNA Disabled |

The project MI holds `Search Service Contributor` + `Search Index Data Contributor` on
the search, so the Agent Service reaches it over AAD (no keys). Verified: the project→search
connection is `auth=AAD` and the capability host provisioned `Succeeded`.

## Networking / access

- Reach private endpoints over the hub **Point-to-Site VPN** (Entra auth). DNS resolves
  via the hub **DNS Private Resolver**; Foundry A-records live in the hub-linked
  `privatelink.*` zones (`rg-mcaps-dns-dev`).
- Foundry private endpoint (spoke): `openai` → `192.168.2.30` (verified in hub
  `privatelink.openai.azure.com`). Validate from a P2S client:
  `nslookup aif-zliorc-pha-dev-ncus-001.openai.azure.com` → `192.168.2.30`.
- **Private image builds for Phase 2:** the in-VNet **ACR Tasks agent pool is NOT deployed**
  — `Microsoft.ContainerRegistry/registries/agentPools` is unavailable in North Central US.
  The private Premium ACR (`crzliorcphadevncus001.azurecr.io`) still exists. Options for
  Phase 2 builds: ACR **cloud Quick Task** (`az acr build`), build locally + `docker push`
  over the VPN, or stand up an agent pool in an adjacent supported region
  (eastus2, canadacentral, swedencentral, francecentral, switzerlandnorth).

## Phase 2 quick start (C# hosted agents)

```csharp
// Uses managed identity / az login (DefaultAzureCredential) — no keys.
var projectEndpoint = "https://aif-zliorc-pha-dev-ncus-001.services.ai.azure.com/api/projects/aifp-zliorc-pha-dev-ncus-001";
var chatDeployment  = "chat";            // gpt-5.4-mini
var embedDeployment = "text-embedding";  // text-embedding-3-large
```

> Running/deploying agents against these private endpoints requires being **on the P2S
> VPN** (or running from an in-VNet compute). Public network access is disabled by design.

## Known residual items

- **Orphaned Central US networking in `rg-pha-dev`.** The prior Central US deploy left an
  un-deletable VNet `vnet-vf2fib-pha-dev-cus-001` (+ 8 NSGs + route table). `agent-subnet`
  is pinned by an orphaned Container Apps `serviceAssociationLink` (`legionservicelink`)
  whose backing managed environment lives in a **Microsoft-managed subscription**
  (`361bf5f5-1c3e-4ff1-87c1-be174b27172b`) — so neither `az group delete` nor the
  create-CAE-then-delete trick can clear it. **Needs a support ticket** to remove the
  platform-side environment. The billable NAT gateway + public IP were deleted; the
  remaining resources are free. This does **not** affect the NCUS deployment.
- **APIM AI Gateway** (`infra/`) is authored but **not yet deployed** (optional, additive).
  After deploy, run `az apim update ... --public-network-access false` (AVM APIM 0.9.1 lacks
  the property — SFI-012 post-step).
- Log Analytics and App Configuration keep key-based local auth (LAW ingestion / App Config
  bootstrap); outside the Cognitive Services/Search tier that MCAPS POLICY-013/SFI-005 gates.
