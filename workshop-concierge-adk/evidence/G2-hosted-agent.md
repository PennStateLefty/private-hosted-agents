# G2 — Hosted Agent Deploy (Microsoft Foundry, private network) — PASS

Proves the ADK/Responses container deploys as a **Microsoft Foundry Hosted Agent**
into the existing private-network Foundry project, becomes **active**, and serves
correct deterministic responses over the private path — **3 consecutive times**.

## Deployed artifact

- Agent: `workshop-concierge:5` — Status **active**
- Agent GUID: `249541d9-aa9c-4343-9ed0-b853ab10a948`
- Instance Identity (IMDS managed identity in container): `9010c509-86f0-462f-abdb-9f954d6ef2f7`
- Image: `crzliorcphadevncus001.azurecr.io/agents/workshop-concierge:v1` (private Premium ACR)
- Project: `aifp-zliorc-pha-dev-ncus-001` (RG `rg-pha-dev`, North Central US)
- Endpoint (responses): `https://aif-zliorc-pha-dev-ncus-001.services.ai.azure.com/api/projects/aifp-zliorc-pha-dev-ncus-001/agents/workshop-concierge/endpoint/protocols/openai/responses?api-version=v1`
- Deploy command (BYO prebuilt image, no oryx/pack build):
  `azd deploy workshop-concierge --from-package crzliorcphadevncus001.azurecr.io/agents/workshop-concierge:v1 --no-prompt`

## Two infra prerequisites discovered & fixed (architecture-preserving)

1. **Private image pull** — `[ImageError] Container registry authentication failed`.
   Root cause: `privatelink.azurecr.io` (in `rg-mcaps-dns-dev`) was linked to the hub
   and demo01 VNets but **not** the spoke `vnet-zliorc-pha-dev-ncus-001`. The
   capability host pulls the image from `agent-subnet` in that spoke (Azure-default
   DNS, `dnsServers=[]`), so the ACR FQDN resolved to a **public** IP that PNA blocks —
   surfaced as an auth failure. Fix: add the spoke VNet link on `privatelink.azurecr.io`
   (mirrors `scripts/post-provision.sh` step 3 for the other BYO hub zones; the single
   zone also holds the `*.northcentralus.data` records, so one link covers both the
   registry and data endpoints). After linking, the platform image pull succeeded and
   the agent reached **active** (poll 4/30).

2. **Model call from container** — inner response `status: failed`,
   `code: server_error`. Container log root cause (via `azd ai agent monitor`):
   `AuthenticationError ... The principal 9010c509-... lacks the required data action
   Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action`.
   The adapter authenticates the model via `DefaultAzureCredential` → in-container this
   is the injected **Instance Identity** managed identity (confirmed in logs:
   "DefaultAzureCredential acquired a token from ManagedIdentityCredential"). Fix:
   grant that identity **Cognitive Services OpenAI User** on the account
   `aif-zliorc-pha-dev-ncus-001` (role includes `.../chat/completions/action`).
   Entra-only auth preserved (`disableLocalAuth=true`, no keys). Cleared after
   data-plane RBAC propagation (~2 min).

## Proof — 3 consecutive successful turns (deterministic behavior verified)

Raw JSON captured under `evidence/g2-runs/run{1,2,3}.json` (all `status: completed`,
`agent_reference.version: 5`).

| Run | Input (role/goal signal) | status | Deterministic result |
| --- | --- | --- | --- |
| 1 | Developer + build an agent | completed | **Build** track ("you're a Developer and your goal is to build an agent") + offers single best alternative |
| 2 | Ambiguous (metrics interest, role/goal not both stated) | completed | Correctly **refuses to guess** — asks for exactly the two required details (role ∈ {Developer, Architect, Business leader}; goal ∈ {Build, Integrate, Govern}) |
| 3 | Platform lead + governance/deployment | completed | **Govern** track ("evaluation, guardrails, identity, observability, AI gateway") + offers single best alternative |

CONSECUTIVE COMPLETED: **3/3**. The tool-driven deterministic recommendation, the
bounded single-alternative continuity, and the clarify-when-underspecified guardrail
all fire correctly through the deployed hosted agent over the private endpoint.

## Reproduce

```
cd workshop-concierge-adk
azd env select wc-dev
azd deploy workshop-concierge --from-package crzliorcphadevncus001.azurecr.io/agents/workshop-concierge:v1 --no-prompt
azd ai agent show workshop-concierge            # Status: active
# 3-run proof:
EP=".../agents/workshop-concierge/endpoint/protocols/openai/responses?api-version=v1"
curl -X POST "$EP" -H "Authorization: Bearer $(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)" \
  -H 'Content-Type: application/json' -d '{"model":"workshop-concierge","input":"..."}'
```
