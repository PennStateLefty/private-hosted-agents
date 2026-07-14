# G3 — Private-network Teams publishing — BLOCKED-EXTERNAL (public ingress DEPLOYED & PROVEN; live round-trip gated on consumption entitlement + Foundry preview authZ)

**Status (2026-07-12, live session):** The public-ingress stack was **deployed live and
proven end-to-end** — the original "offline/deploy-gated" framing below is superseded by
the "Live deployment + findings" section immediately after this. The full chain
`NSG → TLS (Let's Encrypt) → WAF (OWASP 3.2 Prevention) → App Gateway → Foundry private
endpoint` is up and healthy; an unauthenticated probe returns **401 from Foundry** (proving
the request traverses the entire public path and reaches the agent front door). The **WAF
false-positive 403 that broke the Teams handshake was root-caused and fixed**. The **live
channel round-trip could not be completed** — it is gated by two **external** conditions:
(a) Foundry's `activityProtocol` returns **403 on authenticated Bot Framework activities**
(a preview control-plane behavior, unfixable via our auth-scheme/RBAC config), and (b) a
**consumption-entitlement** gap on the M365 Copilot/Teams surface — a Foundry-published
custom-engine agent needs the consumer to hold **either an M365 Copilot license or
tenant-configured pay-as-you-go (Copilot Credits)**; this tenant (E5, no Copilot add-on) had
neither until pay-as-you-go was enabled 2026-07-12, and that entitlement can take **up to 24h**
to propagate. Both are outside this workload's IaC. **Disposition: BLOCKED-EXTERNAL** —
infrastructure COMPLETE and PROVEN; live delivery pending (1) pay-as-you-go entitlement
propagation (retest at 24h) and (2) Foundry-preview `activityProtocol` authZ resolution.

---

## Live deployment + findings (2026-07-12)

The public-ingress exception was authorized and the stack was deployed live into `rg-pha-dev`
(spoke, northcentralus). Everything below was verified on live Azure resources.

### Proven live (objective evidence)

| Layer | Evidence | Result |
| --- | --- | --- |
| Public IP + AGW frontend | `agw-pha-dev`, public IP `135.232.215.129`, FQDN `teams-bot.gutherie-demos.com` | Up |
| TLS | Free ACME (Let's Encrypt) cert via Azure DNS-01, imported to `kv-zliorc-pha-dev-ncus-0`; TLS 1.2 `sslPolicy` | Valid, HTTPS handshake OK |
| WAF | `agw-pha-dev-waf`, OWASP 3.2, **Prevention** mode | Active |
| AGW backend | Foundry private endpoint (host-override `services.ai.azure.com` → `192.168.2.30`) | **Healthy** |
| Unauthenticated probe | `curl` to messaging endpoint, no JWT | **401 from Foundry** (full path traversed, reaches agent front door) |
| Synthetic Bot-Framework-shaped probe | `curl` w/ no `Accept` header + off-domain `serviceUrl` body, post-WAF-fix | **401 3/3** (not 403 → WAF passes bot-shaped traffic) |

### Blocker A — WAF false-positive 403 (ROOT-CAUSED + FIXED, durable)

The original Teams "add → open → loop" was the App Gateway **WAF blocking Bot Framework
POSTs with 403**. Firewall-log analysis showed OWASP anomaly score ≥ 5 from two rules:

- **`920300`** (REQUEST-920-PROTOCOL-ENFORCEMENT — "Missing Accept header"): the Bot
  Framework channel adapter legitimately omits the `Accept` header.
- **`931130`** (REQUEST-931-APPLICATION-ATTACK-RFI — "off-domain reference"): the activity
  JSON legitimately carries an off-domain `serviceUrl` (e.g. `smba.trafficmanager.net`).

**Fix (durable, in IaC):** `infra/bot/app-gateway.bicep` WAF policy now has
`managedRules.ruleGroupOverrides` disabling **920300** and **931130** while **keeping
Prevention mode**. Deployed live (`agw-pha-dev-waf`, both rules `state: Disabled`, verified)
and confirmed by the synthetic probe returning 401 (not 403) with zero firewall matches.

### Blocker B — Foundry `activityProtocol` 403 on authenticated activities (EXTERNAL, preview)

With the WAF passing, an **authenticated** Bot Framework activity (valid `api.botframework.com`
JWT, exercised via the first-class **DirectLine** channel over the same messaging endpoint)
reaches the Foundry backend and Foundry returns **403** ("authenticated but forbidden").
Isolated as a Foundry-side behavior, not ours:

- **AGW forwards fine** — access log shows the adapter POST hitting the backend; the
  **firewall log is empty** for these requests (so it is *not* a WAF block).
- **Independent of auth scheme** — `403` under both `BotServiceTenant` **and**
  `BotServiceRbac` (`authorization_schemes` on `agent_endpoint`).
- **Not fixed by RBAC** — the bot/agent instance identity holds "Cognitive Services OpenAI
  User" **and** "Azure AI Developer"; still 403. ("Azure AI User" role does not exist in tenant.)
- **Not captured in diagnostics** — Foundry `RequestResponse`+`Audit` diagnostic setting
  (`foundry-diag` → LAW) reproduces the 403 with **no log rows** (front-door rejection).

Unauthenticated → 401, authenticated → 403 ⇒ a Foundry **preview control-plane authorization
gap**, unresolvable from our side.

### Blocker C — Teams "add → open → loop" = consumption-entitlement gap (EXTERNAL, admin-fixable)

Foundry's M365 publish surfaces the agent as a **custom-engine agent** in the **Microsoft 365
Copilot** experience. Per Microsoft's own guidance, a per-user Copilot license is **NOT** a hard
requirement — a consumer needs **either** an M365 Copilot license **or** tenant-configured
**pay-as-you-go (Copilot Credits)**; Copilot-licensed users run at no metered charge, everyone
else is metered against Copilot Credits. Sources:
- Foundry `publish-copilot` **Prerequisites** list **no** Copilot license (only Foundry User +
  Azure Bot Service Contributor roles): https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot
- MCS CAT, *"No, You Don't Need a Copilot License to Deploy Agents to Microsoft 365"* — *"Copilot
  Chat … is enough. Your agent's usage is covered through Copilot Credits, not per-user Copilot
  licensing."* https://microsoft.github.io/mcscatblog/posts/no-copilot-license-m365-channel/

This test tenant is **E5 with no Copilot add-on** and had **no pay-as-you-go configured** — i.e.
neither entitlement — which produces exactly the observed "Add → Open → back to Add" loop, and
Teams emits **zero** messaging-endpoint traffic on those clicks (confirmed via AGW access logs —
the loop is upstream of our endpoint, in the M365 Copilot consent/open layer). **Pay-as-you-go
was enabled 2026-07-12 ~17:29 ET**; entitlement propagation to the Teams/Copilot surface can take
**up to 24h** (loop still present at +15 min is expected/inconclusive). **Next action: retest the
add→open flow at the ~24h mark (fully quit Teams first).** This gate is **admin-fixable** — it is
not a hard license purchase.

### FAQ — empty "Bot ID" in the M365 admin-center registration (EXPECTED / cosmetic)

The M365 admin center registration panel shows the **Entra agent ID** populated
(`9010c509-86f0-462f-abdb-9f954d6ef2f7`) and the **Source agent ID** (the Foundry agent ARM
path), but the classic **Bot ID** field is **blank**. This is **expected**, not a defect — the
registration is an **Entra-Agent-ID** publish, so delivery is keyed on the agent's Entra identity
and the legacy Bot ID slot is simply not surfaced. Verified live (2026-07-12, on VPN):

- Azure Bot `bot-pha-dev` — `Succeeded`, `msaAppId 9010c509…`, endpoint = AGW FQDN + activityProtocol path.
- Bot channels — **`MsTeamsChannel` bound** (plus `WebChatChannel`, `DirectLineChannel`).
- Foundry agent endpoint — `protocols: [activity, responses]`; `authorization_schemes: [Entra, BotServiceTenant]`.

The live `BotServiceTenant` auth scheme + bound `MsTeamsChannel` confirm the bot linkage is active.
(There is no read-back API for the persisted `botServiceArmId` — the publish route is POST-only;
`GET .../microsoft365/publish` → 405.) **Conclusion: the empty Bot ID is not the cause of the
add→open→loop** — that traces to Blocker C (entitlement) and downstream Blocker B.

### Net G3 disposition

Ingress infrastructure is **COMPLETE and PROVEN** (Blocker A fixed; full path to Foundry 401).
The **live round-trip is BLOCKED-EXTERNAL** at Microsoft-operated control planes: (B) Foundry
preview `activityProtocol` authZ 403, and (C) M365 Copilot/Teams **consumption entitlement**
(pay-as-you-go enabled 2026-07-12; awaiting ≤24h propagation, then retest). If the loop clears
after propagation but a message still fails to reach the agent, the residual blocker is (B). No
further self-service progress is possible until the pay-as-you-go retest completes and/or a
Foundry-preview support case resolves the `activityProtocol` 403.

### Next-session experiments (paused 2026-07-12 PM — from Graeme Foster's "Foundry Agents … through the Corporate Firewall" blog)

Reference: `techcommunity.microsoft.com/blog/azure-ai-foundry-blog/foundry-agents-and-custom-engine-agents-through-the-corporate-firewall/4502218`.
The article is our exact scenario (Foundry agent behind a private endpoint; Teams/Copilot Channel
Adapters outside). It **confirms** our JWT/transport model and root-causing:

- Inbound token is a **Bot Service JWT** (Microsoft Bot IdP: `iss=https://api.botframework.com`,
  `aud=<Bot App ID>`=`9010c509…`, keys at `https://login.botframework.com/v1/.well-known/openidconfiguration`)
  — **not** an Entra/user identity token.
- Our **401 (no token) → 403 (valid token)** transition proves the token **is reaching Foundry**;
  the 403 is "received-but-forbidden" ⇒ Blocker B is a Foundry-side authZ behavior, not our plumbing.
- **App Gateway is fine as transport** (Foundry validates via the `BotServiceTenant` scheme). The
  article prefers APIM/YARP only when the *perimeter* must validate the Bot JWT (AGW's `validate-jwt`
  handles Entra-issued tokens only). AGW is listed as a valid alternative.

Architecture-preserving experiments to try (none guaranteed to fix Blocker B/C):

1. **Verify spoke egress** allows the outbound **reply** path (silent-failure mode): `smba.trafficmanager.net`,
   `login.microsoftonline.com`, `login.botframework.com`. (Distinct from the inbound WAF 931130 fix.)
2. **Manifest.zip manual bot path** — download the agent manifest and register at `admin.microsoft.com`
   (`learn.microsoft.com/en-us/microsoft-365/agents-sdk/deploy-azure-bot-service-manually`);
   documented workaround for the private-endpoint publish 403; may bypass the add→open→loop.
3. **APIM `validate-jwt` front-door** — reuse existing `apim-pha-dev` (StandardV2, PNA Disabled) with
   the article's inbound policy (audience `9010c509…`, issuer `https://api.botframework.com`) to observe
   the exact inbound token/claims and prove the 403 originates at Foundry.

Also pending: **24h consumption-entitlement retest** (pay-as-you-go enabled 2026-07-12 ~17:29 ET;
fully quit Teams first).

### Clean state restored

All temporary probes reverted to compliant baseline: bot `publicNetworkAccess` → **Disabled**,
agent `authorization_schemes` → `[Entra, BotServiceTenant]`, the temporary "Azure AI Developer"
grant on the bot identity **removed**, temp NSG allow-rule **deleted**, DirectLine secret
scrubbed. **Kept** (durable/beneficial): the WAF rule overrides (Blocker A fix) and the
`foundry-diag` diagnostic setting.

---

## Original framing (pre-live; retained for history)

Publishing the Workshop Concierge to Microsoft Teams requires a **public HTTPS
messaging endpoint** that Microsoft's cloud calls (the Bot Framework channel is not a
private-network path), plus a **Teams Administrator** to approve/publish the app
org-wide. Both are outside this repo's control in the current landing zone:

- `PUBLIC_INGRESS_ENABLED="false"`, `PUBLIC_INGRESS_LIVE="false"`,
  `NETWORK_ISOLATION="true"` (from `landing-zone` azd outputs) — there is **no public
  TLS ingress** deployed, so there is no endpoint to register as the bot's
  `messagingEndpoint`.
- Org-wide Teams app publishing requires **Teams admin** consent.

Per the golden path, this branch is marked **BLOCKED-EXTERNAL**. Everything that can
be built and proven without those external dependencies is done and green.

## What IS built and proven (offline)

| Artifact | Purpose | Status |
| --- | --- | --- |
| `infra/bot/app-gateway.bicep` | App Gateway v2 + WAF public ingress → Foundry agent **private endpoint** (host-override, activityProtocol probe) | `az bicep build` clean |
| `infra/bot/bot-service.bicep` | Azure Bot (SingleTenant, agent principal, PNA Disabled) + `MsTeamsChannel`; endpoint = AGW FQDN + activityProtocol path | `az bicep build` clean |
| `scripts/enable-activity-protocol.sh` | PATCH agent → add `activity` protocol + BotServiceRbac | `bash -n` clean |
| `scripts/create-appgw-subnet.sh` | AGW subnet + NSG (fail-closed: explicit Teams ranges + DenyAllInternetInbound), deploy-gated | `bash -n` clean |
| `scripts/issue-tls-cert.sh` | Free ACME (Let's Encrypt) cert for the listener FQDN via **Azure DNS-01** → import to Key Vault; no service principal (current-session ARM token), deploy-gated | `bash -n` clean |
| `scripts/publish-m365.sh` | Create bot (agent principal) + call Foundry M365 publish API | `bash -n` clean |
| `scripts/publish-teams.sh` | Orchestrate enable-activity → App Gateway → bot → publish, deploy-gated | `bash -n` clean |
| `architecture/decisions/ADR-001-teams-public-ingress.md` | Corrected architecture + sanctioned public-ingress exception | authored |
| `src/bot/messaging.py` + `tests/test_bot_messaging.py` | **Offline artifact only** (not on delivery path — Foundry serves activity natively) | 5 unit tests pass |
| `teams/manifest/manifest.json` | Teams manifest (used only if publishing manually; the M365 publish API builds its own) | JSON-valid |

Adapter contract proven by `test_bot_messaging.py`:
- `conversationUpdate` (or a message with no card value) → intake Adaptive Card, new
  conversation-scoped session, correlation id minted and echoed in
  `channelData.correlationId` **and** threaded onto the card's submit actions.
- `Action.Submit` (activity `value`) → advances the same session and returns the next
  card / final message; correlation id is identical across the whole round trip.
- Acceptance returns "no external system has been changed" + `nextAction:
  enroll_intent:<track>` — the same no-external-commitment guarantee as the agent.
- Sessions are isolated per Teams `conversation.id`.

## Architecture correction (2026-07-12)

An earlier version of this evidence described `src/bot/messaging.py` as "the exact
translation layer the deployed Azure Bot messaging endpoint runs." **That was wrong.**
Foundry Hosted Agents expose the Bot Framework `activity` protocol **natively** at the
agent endpoint (`.../agents/<agent>/endpoint/protocols/activityProtocol`), and Foundry
performs the `validate-jwt` (issuer `https://api.botframework.com`) and end-user RBAC
itself. No custom translator/bot host is required. `src/bot/messaging.py` and
`tests/test_bot_messaging.py` remain as an offline artifact only — they are **not** on the
delivery path. See `architecture/decisions/ADR-001-teams-public-ingress.md`.

The corrected, deploy-gated delivery path:

```
Teams / M365 Copilot → Bot Channel Adapter → Azure Bot Service
  (endpoint = App Gateway FQDN + activityProtocol path)
  → App Gateway v2 + WAF (public IP + TLS)  → Foundry agent PRIVATE endpoint
  (services.ai.azure.com → 192.168.2.30)     → Hosted Agent
```

App Gateway backends to the **Foundry private endpoint** (host-override to
`services.ai.azure.com`), not to a bot host and not to the Azure Bot resource.

## Exact unblock steps (when the public-ingress exception + TLS cert + Teams admin are available)

1. **Obtain the MCAPS public-ingress policy exception** and provision a **TLS certificate**
   for the App Gateway listener FQDN into Key Vault; grant the AGW user-assigned identity
   `Key Vault Secrets User`.
2. **Create the AGW subnet + NSG** (locked to the Teams Bot Channel Adapter ranges):
   ```bash
   PUBLIC_INGRESS_ENABLED=true APPGW_SUBNET_PREFIX=192.168.5.0/26 \
     scripts/create-appgw-subnet.sh   # prints APPGW_SUBNET_ID
   ```
3. **Link `privatelink.services.ai.azure.com`** to the AGW subnet's VNet so the Foundry
   backend FQDN resolves to the private IP (already linked to the spoke in this LZ).
4. **Run the orchestrator** (enable activity protocol → deploy App Gateway → create bot →
   publish to M365):
   ```bash
   PUBLIC_INGRESS_ENABLED=true \
   APPGW_SUBNET_ID=<from step 2> \
   SSL_CERT_KV_SECRET_ID=<kv cert secret id> \
   AGW_UAMI_ID=<agw user-assigned identity resourceId> \
   LISTENER_HOST=<custom domain, optional> \
   LAW_ID=/subscriptions/987a5b92-.../workspaces/log-zliorc-pha-dev-ncus-001 \
     scripts/publish-teams.sh
   ```
5. **Allow outbound** to `smba.trafficmanager.net`, `login.microsoftonline.com`,
   `login.botframework.com` from the agent egress path.
6. **Tenant scope only:** a Microsoft 365 admin approves the app at
   `https://admin.cloud.microsoft/#/agents/all/requested`.
7. **Prove live 3×:** send a message in Teams → receive the recommendation card → accept;
   confirm the correlation id / round trip in App Insights three consecutive times.


## Reproduce (offline proof)

```
cd workshop-concierge-adk && source .venv/bin/activate
python -m pytest tests/test_bot_messaging.py -q   # 5 passed (offline artifact only)
az bicep build --file infra/bot/bot-service.bicep --stdout >/dev/null && echo ok
az bicep build --file infra/bot/app-gateway.bicep --stdout >/dev/null && echo ok
for s in enable-activity-protocol create-appgw-subnet publish-m365 publish-teams; do
  bash -n scripts/$s.sh && echo "ok $s"
done
python -c "import json; json.load(open('teams/manifest/manifest.json'))"
```

