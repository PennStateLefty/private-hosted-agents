# Customer Readiness — Publishing a Private Foundry Hosted Agent to Microsoft Teams (G3)

**Purpose:** what a customer must have ready **before a working session** to stand up public
ingress for a Microsoft Foundry Hosted Agent and publish it to Microsoft Teams / M365 Copilot,
when Foundry and its dependencies are deployed **privately** (public network access disabled).

**Assumptions (given):**
- Microsoft Teams / M365 tenant already set up.
- An Azure **landing zone** exists (hub-and-spoke, private DNS, connectivity).
- **Foundry, the project, and the agent will be deployed privately** (private endpoints, PNA
  disabled) into a spoke.

**Why this is needed:** Teams/M365 message delivery is a **public** Bot Framework path — Microsoft's
channel adapters call your bot from outside your network and cannot reach a private endpoint. The
sanctioned pattern is **App Gateway (public IP + TLS + WAF) → Foundry agent private endpoint**. This
doc lists everything to have in place so the session is spent wiring, not procuring.

> Reference architecture: `architecture/decisions/ADR-001-teams-public-ingress.md`.
> Evidence + exact commands from our reference build: `evidence/G3-teams-publish.md`.

---

## 0. TL;DR readiness checklist (bring these to the session)

| # | Item | Owner | Blocking? |
|---|------|-------|-----------|
| 1 | Public-ingress **governance approval** for this workload (landing-zone exception / sign-off) | Cloud/platform governance | **Yes** |
| 2 | A **public DNS zone you control** + chosen **listener FQDN** for the AGW frontend | DNS/platform | **Yes** |
| 3 | **TLS certificate** for that FQDN staged in **Key Vault** (or ability to auto-issue via DNS-01) | Platform | **Yes** |
| 4 | A **dedicated App Gateway subnet** (≥ /26) in the spoke, with a **fail-closed NSG** | Network | **Yes** |
| 5 | **Private DNS zones** for Foundry/Agent Service linked to the AGW-subnet VNet | Network | **Yes** |
| 6 | **Outbound allow** to `smba.trafficmanager.net`, `login.microsoftonline.com`, `login.botframework.com` | Network | **Yes** |
| 7 | **Foundry project (private) + tested agent + active version selected** | App/AI team | **Yes** |
| 8 | **RBAC**: Foundry User + Azure Bot Service Contributor; `Microsoft.BotService` provider registered | Azure admin | **Yes** |
| 9 | Agent **instance managed identity** granted `Cognitive Services OpenAI User` on the Foundry account | Azure admin | **Yes** |
| 10 | **Consumption entitlement**: Copilot licenses **or** tenant **pay-as-you-go (Copilot Credits)** enabled | M365 Global/Billing admin | **Yes** (≤24h lead) |
| 11 | **Teams app setup/permission policies** allow the published app for target users | Teams admin | **Yes** |
| 12 | **Operator access to the private data path** (VPN / private connectivity) for data-plane steps | Operator | **Yes** |
| 13 | **Region** supports App Gateway v2 **and** Foundry Hosted Agents publishing | Architecture | Verify |
| 14 | **Foundry preview support contact / case path** (see §7 known preview caveat) | Sponsor/CSA | Recommended |

Items **10** and **1** have lead time (entitlement propagation up to 24h; governance approval).
**Start those first.**

---

## 1. Networking — public ingress (the App Gateway path)

1. **Governance / policy exception.** Public ingress is a deliberate exception in most managed
   landing zones. Get the workload sanctioned (a `PUBLIC_INGRESS_ENABLED`-style flag / change
   record). Note: in our reference sub, `az deployment group validate` showed **no Azure Policy
   hard-deny** on a Standard public IP or AGW public frontend — the gate was **process**, not a
   technical deny. **Re-run that `validate` probe under the customer's management-group hierarchy**;
   a corporate MCAPS/ALZ hierarchy may add deny policies you must exempt.
2. **App Gateway v2 subnet.** A dedicated subnet in the spoke, **≥ /26**, no other resources.
3. **Fail-closed NSG** on that subnet: allow inbound **only** from the Bot Framework / Teams
   source ranges (service tag `AzureBotService` / documented Bot Channel Adapter ranges) on 443,
   plus `GatewayManager` health probes; explicit **`DenyAllInternetInbound`**. No broad `AzureCloud`
   allow. Set `defaultOutboundAccess: false` on subnets per landing-zone convention.
4. **TLS listener min 1.2** (`sslPolicy`, e.g. `AppGwSslPolicy20220101`).
5. **Backend = Foundry private endpoint** with a **host-override** to the Foundry data-plane FQDN
   (`<account>.services.ai.azure.com`), and a custom **health probe** against the agent's
   `activityProtocol` path (expect 401/2xx, not 403).

## 2. DNS + TLS

1. **Public DNS**: an Azure Public DNS zone (or delegated zone) you control, and a chosen
   **listener FQDN** (e.g. `teams-bot.<yourdomain>`). An A record will point at the AGW public IP.
2. **TLS cert** for that FQDN in **Key Vault**:
   - Free/automatable: **Let's Encrypt via DNS-01** against the public zone → import to Key Vault
     (our `scripts/issue-tls-cert.sh` does this with the session ARM token, no service principal), **or**
   - Corporate CA / App Service Managed Cert / purchased cert — just get it into Key Vault as a
     secret before the session.
3. **AGW user-assigned identity** with **`Key Vault Secrets User`** on that Key Vault.
4. **Private DNS** — link the Foundry/Agent Service `privatelink.*` zones to the **AGW-subnet VNet**
   (not just the hub) so the backend FQDN resolves to the private IP. Zones seen for Agent Service:
   `privatelink.services.ai.azure.com`, `...openai.azure.com`, `...cognitiveservices.azure.com`,
   `...search.windows.net`, `...blob.core.windows.net`, `...documents.azure.com`. If these aren't
   linked to the spoke, the portal shows *"Error loading your agents"* and the backend won't resolve.

## 3. Foundry project + agent (private)

1. **Private project**: Foundry resource behind a private endpoint, **PNA disabled**. The portal
   one-click publish is **unavailable** in this mode — use the **REST publish flow** (see
   `publish-copilot-virtual-network` and our `scripts/publish-m365.sh` / `publish-teams.sh`).
2. **A tested agent** with an **active version selected**. Confirm it answers correctly in the portal
   first.
3. The publish flow **enables the `activity` protocol** and an **authorization scheme**
   (`BotServiceTenant` for tenant-wide, or `BotServiceRbac` for scoped). Decide the scope up front.

## 4. Azure Bot resource

1. **`Microsoft.BotService` provider registered** (`az provider register --namespace Microsoft.BotService`).
2. **Azure Bot** (SingleTenant), `msaAppId` = the **agent instance managed identity** app/client id,
   **`MsTeamsChannel` enabled**, **PNA Disabled**, messaging endpoint = `https://<listener-FQDN>` +
   the agent `activityProtocol` path.

> **Note — empty "Bot ID" in the M365 admin center is expected.** For an **Entra-Agent-ID**
> publish, the registration panel populates **Entra agent ID** + **Source agent ID** and leaves the
> classic **Bot ID** field blank. This is cosmetic: the real Azure Bot still exists and its
> `MsTeamsChannel` is bound. Confirm the bot is wired via `az bot show` + the bot's channel list
> (expect `MsTeamsChannel`) rather than the admin-center Bot ID field.

## 5. RBAC / identity (have these assigned before the session)

| Principal | Role | Scope |
|-----------|------|-------|
| Operator running publish | **Foundry User** | Foundry project |
| Operator running publish | **Azure Bot Service Contributor** (or Contributor/Owner) | Publish RG |
| Operator | **Key Vault Certificates/Secrets Officer** (to import cert) | Key Vault |
| AGW user-assigned identity | **Key Vault Secrets User** | Key Vault |
| **Agent instance managed identity** | **Cognitive Services OpenAI User** | Foundry account |

> Note: the Foundry RBAC roles were **renamed** — **Foundry User/Owner/Account Owner/Project
> Manager** were formerly **Azure AI User/Owner/Account Owner/Project Manager**. Same role IDs.

## 6. M365 / Teams — consumption entitlement (start early: ≤24h lead)

A Foundry-published agent is a **custom-engine agent** that surfaces in **M365 Copilot / Teams**.
A per-user **Copilot license is NOT a hard requirement**. Each consumer needs **either**:
- an **M365 Copilot license** (runs the agent at no metered charge), **or**
- tenant **pay-as-you-go (Copilot Credits)** configured — a **Global admin or Billing admin** links
  Copilot Credits to a billing/Azure subscription in the **Copilot Studio / Power Platform admin
  center** (surfaced in the M365 admin center). Usage is then metered.

If the tenant has **neither**, users hit an **"Add → Open → loop"** in Teams and the agent never
receives a message. **Enable one of the two before the session** — entitlement propagation to the
Teams/Copilot surface can take **up to ~24h** (often faster). Also confirm **Teams app setup /
permission policies** allow the published app for the target users (and org-catalog publish if
org-wide).

Sources: Foundry `publish-copilot` **Prerequisites** (no Copilot license listed); MCS CAT,
*"No, You Don't Need a Copilot License to Deploy Agents to Microsoft 365."*

## 7. Known preview caveat to validate first (don't get surprised)

In our reference build, after ingress + WAF were proven, an **authenticated** Bot Framework activity
returned **403 from Foundry's `activityProtocol`** (front door), **independent** of auth scheme
(`BotServiceTenant`/`BotServiceRbac`) and of RBAC grants, and **not** captured in Foundry diagnostic
logs. It behaved like a **preview control-plane authorization** gap. Before committing a customer to
a live Teams round-trip in the session:
- Confirm current **preview status/GA** of Foundry Agent Service **publish-to-M365**, and
- Have a **Foundry preview support contact / case path** ready in case the 403 recurs.

## 8. Operator workstation / access

- **Azure CLI + azd**, logged in to the right tenant/subscription.
- **Private data path** to reach the private endpoints for data-plane steps (Foundry PATCH, Key Vault
  import, publish API): the customer's **VPN / ExpressRoute / bastion** path. On **managed macOS**,
  Microsoft **GSA Private Access** can blackhole RFC1918 traffic to private endpoints — disable GSA
  Private Access (keep Internet/M365) while keeping the corporate VPN connected.

---

## 9. Day-of sequence (once the above is ready)

1. Register `Microsoft.BotService`; confirm RBAC (§5).
2. Create AGW subnet + fail-closed NSG (§1).
3. Import/issue TLS cert to Key Vault; grant AGW identity `Key Vault Secrets User` (§2).
4. Link Foundry `privatelink.*` zones to the AGW-subnet VNet (§2.4).
5. Enable `activity` protocol + auth scheme on the agent; deploy App Gateway → Foundry PE;
   create Azure Bot + `MsTeamsChannel`; run the M365 publish (REST flow / `publish-teams.sh`).
6. Add the A record (listener FQDN → AGW public IP); verify backend **Healthy**; an
   **unauthenticated** probe should return **401 from Foundry** (path proven).
7. In Teams: add the agent, open, send a message. Verify the reply.
8. **Prove 3×** and capture correlation ids / App Insights.

## 10. Pre-flight verification (run before declaring ready)

- [ ] `nslookup <account>.services.ai.azure.com` → **private** IP from the operator path.
- [ ] AGW backend health = **Healthy**; unauthenticated probe → **401** (not 403 → WAF OK).
- [ ] Agent answers in the Foundry portal; active version pinned.
- [ ] Consumption entitlement live (a Copilot-licensed test user **or** pay-as-you-go active > ~1h).
- [ ] Target user covered by Teams app setup/permission policy.
- [ ] Foundry publish-to-M365 preview status confirmed / support path ready.
