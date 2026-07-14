# Known Issues & External Blockers

Two gates are `BLOCKED-EXTERNAL`: the code, IaC, and offline proofs are complete, but the
final live step depends on an action outside this workload's control (a landing-zone
toggle or a tenant/admin grant). Everything self-unblockable was completed.

---

## 1. G3 — Live Teams message delivery (BLOCKED-EXTERNAL)

**Architecture (corrected 2026-07-12 — see `architecture/decisions/ADR-001-teams-public-ingress.md`):**
Foundry Hosted Agents serve the Bot Framework `activity` protocol **natively** at the
agent endpoint; Foundry does the JWT validation + RBAC. There is **no custom bot host** —
`src/bot/messaging.py` is an offline artifact only. Delivery path:
`Teams → Bot Channel Adapter → Azure Bot → App Gateway v2 + WAF (public IP + TLS) →
Foundry agent PRIVATE endpoint (services.ai.azure.com → 192.168.2.30) → Hosted Agent`.
App Gateway backends to the Foundry private endpoint (host-override), not to a bot host.

**Status: public ingress DEPLOYED LIVE & PROVEN (2026-07-12).** `agw-pha-dev` (public IP
`135.232.215.129`, FQDN `teams-bot.gutherie-demos.com`) is up with a Let's Encrypt cert
(Azure DNS-01) in `kv-zliorc-pha-dev-ncus-0`, WAF OWASP 3.2 in Prevention, backend to the
Foundry private endpoint **Healthy**. An **unauthenticated** probe returns **401 from
Foundry** — proof the request traverses NSG→TLS→WAF→AGW and reaches the agent front door.

**Blocker A — WAF false-positive 403 (RESOLVED, durable fix in IaC).** The original Teams
"add→open→loop" was the App Gateway WAF returning **403** on Bot Framework POSTs: OWASP rule
**920300** (adapter legitimately omits the `Accept` header) + **931130** (activity JSON
carries an off-domain `serviceUrl` such as `smba.trafficmanager.net`) drove the anomaly score
≥ 5 → block. Fix: `infra/bot/app-gateway.bicep` WAF policy now has
`managedRules.ruleGroupOverrides` disabling **exactly** 920300 + 931130 while **keeping
Prevention mode**. Deployed + verified live (both `state: Disabled`); a synthetic bot-shaped
`curl` (no Accept header, off-domain serviceUrl) returns **401 3/3** with **zero** firewall
matches. **Keep this override** — Bot Framework traffic will always trip these two rules.

**Blocker B — Foundry `activityProtocol` 403 on authenticated activities (EXTERNAL, preview).**
With the WAF passing, an **authenticated** Bot Framework activity (valid `api.botframework.com`
JWT, exercised via the first-class **DirectLine** channel over the same messaging endpoint)
reaches Foundry and Foundry returns **403**. Isolated as Foundry-side, not ours:
- AGW forwards fine (access log shows the POST hit the backend; **firewall log empty** → not WAF).
- Independent of auth scheme — 403 under both `BotServiceTenant` **and** `BotServiceRbac`.
- Not fixed by RBAC — bot identity holds "Cognitive Services OpenAI User" **and** "Azure AI
  Developer"; still 403. (Note: "Azure AI User" was **renamed** to "Foundry User" — it does exist.)
- Not captured in the `foundry-diag` RequestResponse/Audit diagnostic logs (front-door rejection).
Unauthenticated → 401, authenticated → 403 ⇒ a Foundry **preview control-plane authorization**
behavior, unresolvable from our side. **Unblock:** open a Foundry-preview support case with this
evidence; re-test after Foundry Agent Service M365-publish GA.

**Blocker C — M365 Copilot/Teams consumption entitlement (EXTERNAL, admin-fixable).** A
Foundry-published custom-engine agent surfaces in the **M365 Copilot** experience. Per
Microsoft's docs a per-user Copilot **license is NOT a hard requirement** — a consumer needs
**either** a Copilot license **or** tenant-configured **pay-as-you-go (Copilot Credits)**;
licensed users run free, everyone else is metered. (Sources: Foundry `publish-copilot`
Prerequisites list no Copilot license; MCS CAT *"No, You Don't Need a Copilot License to Deploy
Agents to Microsoft 365"*.) This tenant (E5, no add-on) had **neither**, producing the
add→open→loop with **zero** messaging-endpoint traffic (loop is upstream of our endpoint, in the
Copilot consent/open layer). **Pay-as-you-go enabled 2026-07-12 ~17:29 ET**; entitlement can
take **up to 24h** to propagate to the Teams/Copilot surface (loop still present at +15 min is
expected/inconclusive). **Next action: retest add→open at the ~24h mark, fully quitting Teams
first.** If the loop clears but a message still doesn't reach the agent, the residual blocker is B.

**Clean/compliant state restored:** bot `publicNetworkAccess` → Disabled, agent
`authorization_schemes` → `[Entra, BotServiceTenant]`, temp "Azure AI Developer" grant + temp
NSG allow-rule removed, DirectLine secret scrubbed. Kept (durable/beneficial): the WAF rule
overrides (Blocker A fix) and the `foundry-diag` diagnostic setting.

**Compliance remediations applied:** App Gateway pins **min TLS 1.2**
(`sslPolicy` = `AppGwSslPolicy20220101`); the AGW subnet NSG is **fail-closed** (explicit
Teams/Bot Channel Adapter ranges + explicit `DenyAllInternetInbound`, no broad `AzureCloud`
fallback). Zones intentionally omitted: **northcentralus has no availability zones**.

**Full evidence + exact unblock steps:** `evidence/G3-teams-publish.md`. **Customer readiness
prep for a follow-up session:** `docs/CUSTOMER-READINESS-G3-TEAMS.md`.

---

## 2. G5 — Foundry RAI-judge evaluation *run* (BLOCKED-EXTERNAL; corroborated)

**What works:** golden dataset (`tests/golden.jsonl`), `agent/eval.yaml` +
7-dimension custom `wc-quality` evaluator generated by `azd ai agent eval generate`,
and a deterministic scorecard that scores the **deployed** agent **3× at 100%
(36/36)** exact track match (`scripts/eval-scorecard.py`,
`evidence/g5-scorecard-run{1,2,3}.json`).

**Why blocked:** `azd ai agent eval run` fails `400 UnauthorizedUserAction
componentName=raisvc` — the tenant restricts the Responsible AI evaluation service even
for a Foundry **Owner**; it is not self-grantable.

**Unblock:** a tenant admin grants access to the RAI evaluation service (or runs the
judge from an allow-listed subscription). The deterministic scorecard is the
architecture-preserving corroboration in the meantime.

---

## Operational gotchas (resolved, worth knowing)

- **Private DNS must resolve to private IPs.** If model/gateway calls hang or 403, check
  `nslookup aif-…openai.azure.com → 192.168.2.30` and
  `apim-pha-dev.azure-api.net → 192.168.2.26`. On the managed Mac this requires the P2S
  VPN **and** GSA Private Access **disabled**. The macOS resolver may still hand a socket
  the public A record even when `nslookup` shows private — the proof harnesses pin the
  private IP (`APIM_PRIVATE_IP`) with SNI preserved to be deterministic.
- **APIM StandardV2 PNA toggle:** `az apim update --public-network-access false` fails
  `OperationSupportedInSkuForApiVersions`. PATCH via ARM REST api-version
  `2024-06-01-preview` (see `scripts/harden-gateway-inbound.sh`).
- **APIM backend path:** the API inbound path (`openai`) is NOT appended to the backend
  serviceUrl — the backend serviceUrl must itself include `/openai`.
- **`az network private-endpoint create`** uppercases the RG/VNet when given
  `--vnet-name` + short subnet name → `InvalidResourceReference`. Pass the **full**
  `--subnet <id>` and `-l northcentralus`.
- **ACR agent pool** (`Microsoft.ContainerRegistry/registries/agentPools`) is
  unavailable in North Central US → `DEPLOY_ACR_TASK_AGENT_POOL=false`; build via
  `az acr build` / local push.
- **Model:** use `gpt-5.4-mini` on GlobalStandard (gpt-4o is retired / ARM-denied); use
  `max_completion_tokens`, not `max_tokens`.
