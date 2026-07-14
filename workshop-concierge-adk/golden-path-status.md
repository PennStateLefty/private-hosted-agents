# Golden Path Status — Workshop Concierge Foundry Hosted Agent

Durable state file for the autonomous goal in `GOLDEN-PATH-GOAL.md`. Updated after
every material experiment.

_Last updated: 2026-07-12 (G0,G1,G2,G4,G5,G6,G7,G8 PASS; G3 BLOCKED-EXTERNAL — public-ingress stack DEPLOYED & PROVEN live, WAF 403 fixed; live round-trip gated on two external gaps: M365 consumption entitlement + Foundry preview activityProtocol 403; golden path complete, capstone proven 3/3 end-to-end over the private path)_

> **Network state:** P2S VPN connected + GSA Private Access disabled →
> `aif-...services.ai.azure.com` resolves to private endpoint `192.168.2.31`
> and live Foundry model calls succeed (Entra-only). Live gates are now
> executable rather than BLOCKED-EXTERNAL, while the VPN stays connected.

## Gate table

| Gate | Title | Status | Evidence | Notes |
| ---- | ----- | ------ | -------- | ----- |
| G0 | Repository & environment baseline | PASS | `evidence/G0-*.md` | 60 tests, env + PNA inventory, private DNS proven |
| G1 | Local Responses adapter | PASS | `evidence/G1-responses-adapter.md` | Contract tests + linux/amd64 container (60) + live D1 model path |
| G2 | Foundry Hosted Agent deployment | PASS | `evidence/G2-hosted-agent.md` | `workshop-concierge:5` active; 3/3 completed turns over private endpoint; azurecr.io spoke DNS link + OpenAI User grant on instance MI |
| G3 | Private-network Teams publishing | BLOCKED-EXTERNAL | `evidence/G3-teams-publish.md`, `architecture/decisions/ADR-001-teams-public-ingress.md` | **Public-ingress stack DEPLOYED LIVE & PROVEN** (2026-07-12): `NSG → TLS (Let's Encrypt/Azure DNS-01) → WAF (OWASP 3.2 Prevention) → App Gateway `agw-pha-dev` (public IP `135.232.215.129`, FQDN `teams-bot.gutherie-demos.com`) → Foundry private endpoint` — backend **Healthy**, unauthenticated probe → **401 from Foundry** (full path reaches agent front door). **WAF false-positive 403 root-caused + FIXED** (durable, in `app-gateway.bicep`): `ruleGroupOverrides` disable rules **920300** (bot omits Accept header) + **931130** (off-domain `serviceUrl`), Prevention mode kept; synthetic bot-shaped probe → 401 3/3, zero firewall matches. **Live round-trip NOT completed — two EXTERNAL gaps:** (B) Foundry `activityProtocol` returns **403 on authenticated activities** (via DirectLine), independent of auth scheme (`BotServiceTenant`/`BotServiceRbac`) and RBAC (OpenAI User + Azure AI Developer both present) — a preview control-plane behavior, not captured in Foundry diag logs; (C) M365 Copilot/Teams **consumption entitlement** — custom-engine agent needs consumer to hold a Copilot license **or** tenant **pay-as-you-go (Copilot Credits)**; tenant (E5, no add-on) had neither → add→open→loop, **pay-as-you-go enabled 2026-07-12 ~17:29 ET**, ≤24h to propagate → **retest at 24h**. Clean/compliant state restored (bot PNA Disabled, auth scheme reverted, temp grants/NSG removed) |
| G4 | Adaptive Card + callback correlation | PASS | `evidence/G4-adaptive-card.md` | `teams_dispatch` threads one correlation id intake→recommend→alternative→accept; bounded single-alt + no-external-commit enforced across callback boundary; 6 dispatch tests + full suite 88 passed 3/3 (live Teams delivery = G3) |
| G5 | Foundry evaluation | PASS | `evidence/G5-evaluation.md` | Prepared golden dataset; Foundry eval suite + 7-dim custom evaluator authored; deterministic scorecard 3/3 @100% (36/36) on live agent; RAI judge *run* BLOCKED-EXTERNAL (raisvc Forbidden despite Foundry Owner) |
| G6 | Agent guardrail | PASS | `evidence/G6-guardrail.md` | ADK before_model guardrail (injection/exfiltration/off-scope) shipped in v2 → agent v6; 22 unit tests + 3/3 live blocked, valid flow intact |
| G7 | APIM AI Gateway | PASS | `evidence/G7-ai-gateway.md` | `apim-pha-dev` StandardV2 (VNet-integrated, system-MI auth, no keys) in front of private Foundry; token-limit governance proven **3/3 over the private path** (enforce→429, restore→200 real completion). Inbound fully private: `publicNetworkAccess=Disabled` + PE `pe-apim-pha-dev` (Approved) via `privatelink.azure-api.net` → 192.168.2.26 |
| G8 | Repeatable capstone | PASS | `evidence/G8-capstone.md` | End-to-end (deployed-agent routing + live guardrail + APIM governance) proven **3/3 over the private path** via `scripts/capstone-proof.py`; offline suite 93 passed 3/3; final deliverables `DEMO-SCRIPT.md`/`KNOWN-ISSUES.md`/`CLEANUP.md`/`FINAL-REPORT.md` |

Status legend: `PASS` · `IN-PROGRESS` · `PENDING` · `FAIL` · `FAIL-HARD` ·
`BLOCKED-EXTERNAL`.

## Environment (discovered)

| Input | Value | Source |
| ----- | ----- | ------ |
| `AZURE_SUBSCRIPTION_ID` | `987a5b92-2573-4981-a76c-bbd7756592c8` (`ME-MngEnvMCAP438243-jgutherie-1`) | `az account show` |
| `AZURE_TENANT_ID` | `eba3295c-9080-423b-9a22-346e7ed2c3bd` | `az account show` |
| `AZURE_RESOURCE_GROUP` | `rg-pha-dev` | PHASE1-HANDOFF |
| `AZURE_LOCATION` | `northcentralus` | PHASE1-HANDOFF |
| `AZURE_FALLBACK_LOCATION` | `eastus2` (candidate; validate capacity) | PHASE1-HANDOFF region note |
| `FOUNDRY_RESOURCE_NAME` | `aif-zliorc-pha-dev-ncus-001` | PHASE1-HANDOFF |
| `FOUNDRY_PROJECT_NAME` | `aifp-zliorc-pha-dev-ncus-001` | PHASE1-HANDOFF |
| `FOUNDRY_PROJECT_ENDPOINT` | `https://aif-zliorc-pha-dev-ncus-001.services.ai.azure.com/api/projects/aifp-zliorc-pha-dev-ncus-001` | PHASE1-HANDOFF |
| `MODEL_DEPLOYMENT_NAME` | `chat` (`gpt-5.4-mini`, GlobalStandard) | PHASE1-HANDOFF |
| `AGENT_REPO_NAME` | `workshop-concierge-adk` | this workload dir |
| `PRIVATE_TEST_HOST` | local Mac over P2S VPN (GSA-gated) | this session |
| `APIM_INSTANCE_NAME` | INPUT-REQUIRED (authored in `../infra/`, not deployed) | PHASE1-HANDOFF |
| `TEAMS_INGRESS_FQDN` | INPUT-REQUIRED | — |
| `TEAMS_TEST_USER` | INPUT-REQUIRED | — |

## Auth state

- `az` CLI: signed in as `jgutherie@microsoft.com`, subscription `ME-MngEnvMCAP438243-jgutherie-1`.
- `azd`: signed in as `admin@MngEnvMCAP438243.onmicrosoft.com` (same tenant/sub).
- `microsoft.foundry` azd extension installed `0.1.0-preview`; `azure.ai.agents`
  `0.1.8-preview` (goal G5 wants `azure.ai.agents >= 0.1.40-preview` — UPGRADE REQUIRED).

## Known blocker — private DNS not resolving to private endpoint

`nslookup aif-zliorc-pha-dev-ncus-001.openai.azure.com` currently returns the **public**
APIM traffic-manager address `20.125.164.145`, not the private endpoint `192.168.2.30`.
The Foundry resource has public network access **disabled**, so model/eval calls will fail
until the private path is active.

- **Unblock:** on the managed Mac, disable Global Secure Access (GSA) *Private Access*
  profile (keep Internet Access + M365) and keep the Azure P2S VPN connected, then confirm
  `nslookup … → 192.168.2.30`. Requires the user to be present at the workstation.
- **Impact:** gates that require live private-network calls (G2 model call, G5 evaluation,
  parts of G7) are `BLOCKED-EXTERNAL` on this until resolved. All net-new code, tests,
  container build, IaC, azd scaffolding, and docs proceed independently.

## azd isolation decision (user requirement)

The infrastructure azd project lives at `landing-zone/azure.yaml` (`name: azure-ai-lz`,
env `pha-dev`). The agent gets its **own** azd project rooted at
`workshop-concierge-adk/azure.yaml` with its **own** `.azure/` env, so `azd` never
resolves the two together. azd only searches upward for the nearest `azure.yaml`; the two
projects live in sibling/child directories and share no env state. See
`architecture/decisions/ADR-000-azd-isolation.md`.

## Current hypothesis / next action

Build all net-new, locally-verifiable artifacts first (G0 ADK agent + tests, G1 adapter +
container, azd project, bicep, scripts, docs), capturing evidence. Then attempt live
gates; mark private-network-dependent proofs `BLOCKED-EXTERNAL` with exact unblock steps.

## Change log

- 2026-07-10: Initialized status file, gate table, environment discovery, azd-isolation
  decision, private-DNS blocker recorded.
- 2026-07-10: Private path went ACTIVE (VPN + GSA disabled). G0 + G1 PASS (60 tests,
  linux/amd64 container, live D1 ADK→Foundry model call).
- 2026-07-10: **G2 PASS.** Hosted agent `workshop-concierge:5` deployed via isolated azd
  project (`wc-dev` env) using BYO image `crzliorcphadevncus001.azurecr.io/agents/workshop-concierge:v1`
  and `azd deploy --from-package`. Two infra prereqs found & fixed (architecture-preserving):
  (1) linked `privatelink.azurecr.io` to the spoke VNet so the agent-subnet sandbox pulls the
  image privately (already covered idempotently by `scripts/post-provision.sh` zone loop);
  (2) granted the agent **instance** managed identity `Cognitive Services OpenAI User` on the
  Foundry account so the container's DefaultAzureCredential model call succeeds Entra-only
  (new `workshop-concierge-adk/scripts/grant-agent-model-access.sh`). Proven **3/3**
  consecutive completed responses with correct deterministic track routing.

- 2026-07-10: **G5 PASS.** Authored 12-case deterministic golden dataset
  (`tests/golden.jsonl`) + `scripts/eval-scorecard.py`; live deployed agent scored
  **3/3 @ 100% (36/36)** exact track-match. `azd ai agent eval generate` produced
  `agent/eval.yaml` + 7-dimension custom `wc-quality` evaluator. The RAI-judge *run*
  (`azd ai agent eval run`) is **BLOCKED-EXTERNAL**: `400 UnauthorizedUserAction
  componentName=raisvc` even as Foundry Owner (tenant RAI restriction, not
  self-grantable). PASS via deterministic scorecard fallback.
- 2026-07-10: **G6 PASS.** Added ADK `before_model_callback` input guardrail
  (`src/workshop_concierge/guardrail.py`: instruction-override / exfiltration /
  off-scope) shipped in image `v2` → hosted agent **version 6 active**. 22 unit tests +
  live `scripts/guardrail-proof.py` **3/3** (4 adversarial inputs blocked, valid input
  still routes to Build). Instance identity stable across versions → existing RBAC grant
  sufficed.
- 2026-07-10: **G4 PASS.** `src/workshop_concierge/teams_dispatch.py` — pure Adaptive
  Card callback dispatcher that threads a single correlation id end-to-end
  (intake→recommend→alternative→accept), enforcing bounded single-alternative and
  no-external-commitment across the callback boundary. 6 dispatch tests + full suite
  **88 passed 3/3** (`evidence/g4-suite-3x.txt`). Live Teams delivery deferred to G3.

- 2026-07-10: **G3 BLOCKED-EXTERNAL.** Authored the full Teams delivery stack —
  `src/bot/messaging.py` (Bot Framework Activity ⇄ `teams_dispatch` adapter, 5 tests),
  `infra/bot/bot-service.bicep` (Azure Bot UserAssignedMSI + MsTeamsChannel, builds
  clean), `teams/manifest/manifest.json` (v1.16, valid), `scripts/publish-teams.sh`
  (idempotent). Live delivery blocked by landing-zone `PUBLIC_INGRESS_ENABLED=false`
  (no public TLS messaging endpoint) + Teams-admin org publish. Exact unblock steps in
  `evidence/G3-teams-publish.md`.
- 2026-07-10: **G7 PASS.** Created dedicated APIM subnet `apim-subnet`
  (192.168.4.0/27, delegated Microsoft.Web/serverFarms, defaultOutbound=false) + NSG
  `nsg-apim-pha-dev` (APIM v2 required rules) in the spoke; adapted
  `infra/modules/ai-gateway.bicep` for `virtualNetworkType=External` + optional UAMI
  (USE_UAI=false). APIM StandardV2 (`apim-pha-dev`) deployed with outbound VNet
  integration to the private Foundry endpoint; API `azure-openai` + `azure-openai-token-limit`
  policy authenticating to the backend via the APIM **system MI** (`Cognitive Services
  OpenAI User`, no keys). Governance proven **3/3** (enforce tpm=100→429 with
  `x-ratelimit-remaining-tokens`; restore tpm=20000→200 real completion) via
  `scripts/gateway-proof.py`. **Inbound hardening completed:** private endpoint
  `pe-apim-pha-dev` (conn Approved) wired to BYO `privatelink.azure-api.net`
  (hub+spoke linked → 192.168.2.26) and `publicNetworkAccess=Disabled` (public callers
  now 403); governance **re-proven 3/3 over the private path** (harness pins the PE IP
  with SNI preserved). `scripts/harden-gateway-inbound.sh` captures the exact steps
  (full-subnet-id PE create `-l northcentralus`; PNA disable via ARM REST
  api-version 2024-06-01-preview since the CLI version is unsupported on StandardV2).
- 2026-07-10: **G8 PASS — golden path complete.** Authored `scripts/capstone-proof.py`:
  one repeatable harness that, per run, (1) calls the DEPLOYED hosted agent over its
  private Responses endpoint and asserts correct track routing (G2/G4), (2) sends an
  injection prompt to the same agent and asserts the deterministic guardrail refusal
  (G6), and (3) drives the APIM AI gateway enforce→429 / restore→200 over the inbound
  **private endpoint** (G7). All three must pass; ran **3/3 consecutive end-to-end PASS**
  (`evidence/g8-capstone-run{1,2,3}.json`). Offline suite **93 passed 3/3**
  (`evidence/g8-suite-3x.txt`). Final deliverables written: `DEMO-SCRIPT.md`,
  `KNOWN-ISSUES.md`, `CLEANUP.md`, `FINAL-REPORT.md`, `evidence/G8-capstone.md`. Remaining
  external items unchanged: G3 live Teams delivery + G5 RAI-judge run (both with exact
  unblock steps documented). Final gate tally: **8/9 PASS, 1 BLOCKED-EXTERNAL**.
- 2026-07-12: **G3 architecture corrected + App Gateway path authored (still BLOCKED-EXTERNAL).**
  Verified against the Foundry private-network publish guide that Hosted Agents serve the
  Bot Framework `activity` protocol **natively** (`.../agents/<agent>/endpoint/protocols/activityProtocol`)
  and Foundry performs the validate-jwt (issuer api.botframework.com) + end-user RBAC itself —
  so **no custom bot host is needed**. The earlier assumption that `src/bot/messaging.py` must
  be hosted as the messaging endpoint was wrong; it is now labelled an offline artifact only.
  Authored the corrected, deploy-gated public-ingress stack: `infra/bot/app-gateway.bicep`
  (public IP + WAF_v2 + TLS listener + backend → **Foundry private endpoint** with host-override
  + activityProtocol health probe), revised `infra/bot/bot-service.bicep` (SingleTenant, msaAppId =
  agent principal, PNA Disabled, endpoint = App Gateway FQDN + activityProtocol path), and scripts
  `enable-activity-protocol.sh` / `create-appgw-subnet.sh` / `publish-m365.sh` / rewritten
  `publish-teams.sh` orchestrator (all gated behind `PUBLIC_INGRESS_ENABLED=true`). Both bicep
  files `az bicep build` clean; all scripts `bash -n` clean. New `architecture/decisions/ADR-001-teams-public-ingress.md`
  records the sanctioned public-ingress exception. Not deployed — live delivery remains blocked by
  3 external gates: MCAPS public-ingress policy exception, a TLS certificate, and Teams/M365 admin
  approval (exact unblock steps in `evidence/G3-teams-publish.md`).
- 2026-07-12: **G3 gate re-assessment — public-ingress is NOT a policy hard-block; cert path solved.**
  Ran the `compliance-check` agent on `infra/bot/{app-gateway,bot-service}.bicep`. It proved
  **empirically** (via `az deployment group validate`, which runs the full policy engine) that this
  subscription has **no Azure Policy denying the Standard public IP or the App Gateway public
  frontend** — 11 assignments, all Defender/ASC; 0 deny-effect; 0 exemptions; 0 denyAssignments;
  `validate` on a Standard static public IP returned `error: null`. So the "public-ingress exception"
  is a **process/governance gate** (`PUBLIC_INGRESS_ENABLED` + operator authorization, ADR-001), **not**
  a technical deny requiring a policy exemption here. Also confirmed the **Teams/M365 admin approval is
  not required** (portal shows no pending request). Discovered a **public DNS zone we control**
  (`gutherie-demos.com`, rg-mcaps-dns-dev) → the TLS cert is now solvable with a **free ACME
  (Let's Encrypt) cert via Azure DNS-01**: added `scripts/issue-tls-cert.sh` (deploy-gated, no service
  principal — uses the current session's ARM token — imports to `kv-zliorc-pha-dev-ncus-0`). Applied the
  two compliance FAIL fixes: App Gateway now pins **min TLS 1.2** (`sslPolicy` AppGwSslPolicy20220101) and
  the AGW subnet NSG is **fail-closed** (explicit Teams ranges required + explicit `DenyAllInternetInbound`;
  no broad `AzureCloud` fallback). Zones intentionally omitted (spoke region **northcentralus has no AZs**).
  `az bicep build` + `bash -n` still clean. Net: G3's blockers reduce to operator authorization to flip
  `PUBLIC_INGRESS_ENABLED=true`, the private data path (VPN + GSA Private Access off) for the data-plane
  steps, and a 3× channel round-trip proof. Not yet deployed — awaiting go/no-go to execute the live path.
- 2026-07-12 (live): **G3 public-ingress DEPLOYED LIVE + WAF 403 fixed; live round-trip hits two external gaps.**
  Executed the sanctioned public-ingress path: deployed `agw-pha-dev` (public IP `135.232.215.129`, FQDN
  `teams-bot.gutherie-demos.com`), issued a free Let's Encrypt cert via Azure DNS-01 into
  `kv-zliorc-pha-dev-ncus-0`, WAF OWASP 3.2 in Prevention. Backend to the Foundry private endpoint is
  **Healthy**; an unauthenticated probe returns **401 from Foundry** — the request traverses NSG→TLS→WAF→AGW
  and reaches the agent front door. **Root-caused + fixed the WAF false-positive 403** that broke the Teams
  handshake: OWASP rules **920300** (Bot Framework adapter omits the `Accept` header) and **931130** (activity
  JSON carries an off-domain `serviceUrl` like `smba.trafficmanager.net`) pushed the anomaly score ≥ 5 → block.
  Added `managedRules.ruleGroupOverrides` to `infra/bot/app-gateway.bicep` disabling exactly those two rules
  while **keeping Prevention mode**; deployed + verified live (both `state: Disabled`); synthetic bot-shaped
  `curl` → **401 3/3** with **zero** firewall matches. **Two remaining blockers, both EXTERNAL:** (B) an
  authenticated Bot Framework activity (exercised via the first-class DirectLine channel over the same
  messaging endpoint) reaches Foundry and Foundry returns **403** — AGW forwards fine (firewall log empty),
  independent of auth scheme (`BotServiceTenant` **and** `BotServiceRbac` both 403), not fixed by RBAC (bot
  identity holds "Cognitive Services OpenAI User" **and** "Azure AI Developer"), and **not captured** in the
  `foundry-diag` RequestResponse/Audit logs (front-door rejection). ⇒ a Foundry **preview control-plane authZ**
  behavior. (C) The Teams add→open→loop is a **consumption-entitlement** gap: a Foundry-published custom-engine
  agent surfaces in the M365 Copilot experience; per Microsoft docs a consumer needs **either** an M365 Copilot
  license **or** tenant **pay-as-you-go (Copilot Credits)** — **not** a hard license (earlier "Copilot license
  required" assessment CORRECTED; sources: Foundry `publish-copilot` prerequisites list none; MCS CAT blog).
  Tenant (E5, no add-on) had neither; **pay-as-you-go enabled 2026-07-12 ~17:29 ET**, ≤24h to propagate →
  **retest add→open at the 24h mark** (fully quit Teams first). Restored clean/compliant state (bot PNA
  Disabled, agent `authorization_schemes` → `[Entra, BotServiceTenant]`, temp "Azure AI Developer" grant +
  temp NSG rule removed, DirectLine secret scrubbed). Kept durable: the WAF overrides + `foundry-diag`.
  Customer-side prep for the Tuesday follow-up: `docs/CUSTOMER-READINESS-G3-TEAMS.md`.
