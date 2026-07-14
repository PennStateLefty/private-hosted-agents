# Phase 1 setup — lessons learned & template improvements

This captures **what it actually took** to stand up a private-networked Foundry +
Agent Service environment for hosted agents in the MCAPS `mcaps-foundation` landing
zone, and the **specific changes to fold back into the `mcaps-demo-template`** (mostly
the agent + skill definitions) so the next demo skips this troubleshooting.

It is written to be actionable: every gotcha below ends with a **Template action**
naming the file that should carry the fix.

---

## TL;DR — the things that cost us time

1. **Region matters more than the template implies.** Hosted Agents v2 is only in a few
   regions, and Central US (the template default) is **not** one of them.
2. **`ACR Tasks agent pool` isn't available in every region** — it blocked the deploy in
   North Central US until disabled.
3. **Private DNS zones must be linked to the SPOKE, not just the hub.** Missing spoke links
   = the portal's "Error loading your agents" (Agent Service can't resolve Cosmos/Search).
4. **On a managed Mac, Global Secure Access (GSA) Private Access silently hijacks private
   traffic** and blackholes TLS to Azure private endpoints — it looks like an MTU/VPN bug
   but isn't.
5. **macOS split-DNS** means `curl` can resolve a private hostname to the *public* IP even
   with the VPN up — you must pin the private IP to test.

---

## What we built (one paragraph)

An MCAPS-compliant, **private-networked** Microsoft Foundry account + project + Agent
Service (AI Search + Cosmos + Storage + Key Vault + private ACR), deployed as a **spoke**
(`192.168.0.0/21`) global-peered into the existing Central US hub (`vnet-mcaps-hub-dev`),
using **azd** + the vendored `bicep-ptn-aiml-landing-zone` in `ailz-integrated` mode.
Public network access disabled everywhere, Entra-only auth, reachable over the hub P2S VPN.
Region: **North Central US** (see below). Live handles: [`docs/PHASE1-HANDOFF.md`](PHASE1-HANDOFF.md).

---

## Gotchas, root causes, and fixes

### 1. Region: Hosted Agents v2 is region-limited (Central US ≠ supported)

- **Symptom:** everything deploys in Central US, but Hosted Agents v2 features aren't
  available; the capability host / hosted-agents runtime is a no-go.
- **Root cause:** Hosted Agents v2 ships in a limited region set. Central US — the template's
  default region — is not in it. See the
  [regions list](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents#limits-pricing-and-availability).
- **Fix:** deploy the **workload spoke** to a Hosted-Agents-v2 region. We used **North
  Central US** (also had AI Search `standard` capacity when Sweden Central / East US 2 were
  exhausted with `InsufficientResourcesAvailable`). The **hub stays in Central US**; global
  VNet peering + global private DNS zones bridge the regions. Model quota is subscription-
  global, so no per-region quota move was needed.
- **Template action:** `scaffold-demo` agent — the "default Central US" guidance needs a
  **Foundry/hosted-agents caveat**: for hosted-agents demos, pick a Hosted-Agents-v2 region
  for the spoke and verify AI Search `standard` capacity there first. `mcaps-compliance`
  skill region gate should note that a hub in Central US + a spoke in another region is a
  supported, expected pattern here.

### 2. `ACR Tasks agent pool` is not available in every region

- **Symptom:** deploy fails creating `Microsoft.ContainerRegistry/registries/agentPools` in
  North Central US.
- **Root cause:** in-VNet ACR Tasks agent pools aren't offered in NCUS (region gap, not a
  quota/policy issue).
- **Fix:** set `DEPLOY_ACR_TASK_AGENT_POOL=false`. The private Premium ACR still deploys.
  Phase 2 image builds use ACR cloud Quick Task (`az acr build`), local `docker push` over
  the VPN, or an agent pool in an adjacent supported region.
- **Template action:** `scripts/configure-azd-env.sh` already encodes this for NCUS. Add a
  one-line note to `scaffold-demo` step 4 (ACR build path): **check `agentPools` region
  availability; disable the in-VNet pool if unsupported and fall back to `az acr build`.**

### 3. Private DNS zones must be linked to the SPOKE ("Error loading your agents")

- **Symptom:** Foundry portal loads, but creating/opening a prompt agent spins ~30s then:
  *"Error loading your agents … Request ID …"*. Classic private-DNS resolution failure.
- **Root cause:** the spoke VNet uses **Azure-default DNS** (`dhcpOptions.dnsServers = []`).
  The `privatelink.*` zones (`rg-mcaps-dns-dev`) were linked to the **hub** only. Agent
  Service containers run in the **spoke's** `agent-subnet` and resolve via Azure DNS →
  couldn't resolve the Cosmos / Search / Storage private endpoints.
- **Fix:** link every relevant zone (`documents`, `search`, `blob`, `openai`,
  `cognitiveservices`, `services.ai`) to the **spoke** VNet (`--registration-enabled false`).
  Additive and immediate — no restart; Azure-default DNS picks up linked zones instantly.
- **Template action (already partly done):** `scripts/post-provision.sh` now has a **Step 3**
  that loops the `privatelink*` zones in the DNS RG and links each to the spoke VNet. Keep
  this. The `scaffold-demo` agent's DNS step currently says only *"auto-link to the hub's
  private DNS zones"* — **that is insufficient**; update it to require linking zones to **both
  hub and spoke** whenever the spoke uses Azure-default DNS.

### 4. macOS + GSA Private Access silently hijacks private traffic (the real "VPN" bug)

- **Symptom:** P2S VPN connected, routes present, `nslookup` returns the private IP — but
  `curl` to a private endpoint TCP-"connects" in ~30ms then TLS **blackholes ~5s** and fails.
  `sudo tcpdump -ni utun9` (the Azure VPN interface) shows **zero packets** for the flow.
- **Root cause:** the **Microsoft Global Secure Access** client's **Private Access** profile
  transparently proxies RFC1918-destined flows *above* the routing table (transparent-proxy
  intercept). It fakes the TCP connect and never puts the packets on the VPN tunnel → TLS
  blackholes. **This is not MTU** — we chased MTU (1350/1200) first and it changed nothing.
- **Fix:** disable **GSA Private Access only** (keep Internet Access + M365 so the managed-
  device requirement is preserved). Toggling GSA resets the network stack and **drops the
  Azure VPN** — reconnect with `scutil --nc start "vnet-mcaps-hub-dev"` (cached P2S creds).
  Working combo = **Azure VPN connected AND GSA Private Access off**.
- **Template action:** this is client/environment, not IaC — belongs in a **connectivity
  troubleshooting** section of the `mcaps-compliance` skill (or a `docs/CONNECTIVITY.md`
  the template ships). Symptom→cause→fix as above. Already stored as a user memory.

### 5. macOS split/scoped DNS → `curl` resolves the PUBLIC IP

- **Symptom:** `nslookup foundry.openai.azure.com` returns the private `192.168.2.x`, but
  `curl` / `getaddrinfo` hits the public IP and fails against a PNA-disabled endpoint.
- **Root cause:** macOS scoped resolvers — the VPN pushes resolver `10.0.1.4` but only for
  its match-domains. `*.openai.azure.com` isn't in the VPN's match-domain list, so the system
  resolver answers from public DNS.
- **Fix (for testing):** pin the private IP —
  `curl --resolve <acct>.openai.azure.com:443:192.168.2.30 ...`. For real workloads, rely on
  the private endpoint + linked zones (which is why #3 matters).
- **Template action:** same connectivity troubleshooting section as #4; include the
  `curl --resolve` one-liner as the canonical private-endpoint smoke test.

### 6. AI Search Entra-only from first deploy (fixed in the template — keep it)

- **Note:** an earlier deploy needed live remediation to make AI Search Entra-only. The
  vendored `landing-zone/main.bicep` now sets `disableLocalAuth: true` + `authOptions: null`
  on **both** search blocks, so NCUS was compliant from the first deploy — **no live fix
  needed.** Don't regress this.
- **Template action:** `compliance-check` agent should keep AI Search `disableLocalAuth` +
  `authOptions: null` in its auth gate (POLICY-013 / SFI-005).

### 7. Teardown can be blocked by a Microsoft-side serviceAssociationLink

- **Symptom:** `az group delete` hangs on `agent-subnet`; a `serviceAssociationLink`
  (`legionservicelink`) pins the subnet and its backing managed environment lives in a
  **Microsoft-managed subscription** — you can't delete it.
- **Fix:** don't fight it. Redeploy into the **same RG with a new resource token** (no name
  collision), delete only the billable orphans (NAT gateway + public IP), and open a support
  ticket for the platform-side leftover.
- **Template action:** note in `scaffold-demo` / runbook that **relocating a hosted-agents
  deploy may strand a Microsoft-owned SAL**; prefer getting the region right up front (#1).

---

## Template change backlog (mapped to files)

| # | Lesson | Target file in template | Change |
| --- | --- | --- | --- |
| 1 | Hosted Agents v2 region-limited | `.github/agents/scaffold-demo.md`, `mcaps-compliance` skill (region gate) | Add Foundry/hosted-agents region caveat; verify AI Search `standard` capacity; hub-CUS + spoke-elsewhere is expected |
| 2 | ACR agent pool region gap | `.github/agents/scaffold-demo.md` (ACR step), `scripts/configure-azd-env.sh` | Check `agentPools` availability; disable + fall back to `az acr build` |
| 3 | Spoke DNS zone linking | `.github/agents/scaffold-demo.md` (DNS step), `scripts/post-provision.sh` | Require linking `privatelink.*` zones to **hub AND spoke** when spoke uses Azure-default DNS (post-provision Step 3 already does this) |
| 4 | GSA Private Access hijack | `mcaps-compliance` skill or `docs/CONNECTIVITY.md` | Connectivity troubleshooting: symptom (tcpdump silent on utun9) → disable GSA Private Access → `scutil --nc start` reconnect |
| 5 | macOS split DNS | `mcaps-compliance` skill or `docs/CONNECTIVITY.md` | Canonical private smoke test: `curl --resolve host:443:<privIP>` |
| 6 | Search Entra-only | `.github/agents/compliance-check.md` | Keep AI Search `disableLocalAuth:true` + `authOptions:null` in the auth gate |
| 7 | SAL-blocked teardown | `.github/agents/scaffold-demo.md` / runbook | Warn that relocation strands a MS-owned SAL; get region right first |

---

## Suggested concrete edits (drop-in wording)

**`scaffold-demo.md` — step 1 (region):**

> **Confirm target region.** Default **Central US** for generic demos. **For Foundry
> *hosted-agents* demos, the spoke must be in a Hosted Agents v2 region** (Central US is
> NOT supported) — pick one from the
> [regions list](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents#limits-pricing-and-availability)
> and confirm AI Search `standard` capacity there before deploying. The hub stays in
> Central US; global peering + global DNS bridge the regions.

**`scaffold-demo.md` — step 3 (DNS), replace "auto-link to the hub's private DNS zones":**

> …and **link every `privatelink.*` zone the spoke uses to BOTH the hub VNet AND the spoke
> VNet** (`--registration-enabled false`). The spoke uses Azure-default DNS, so unlinked
> zones cause Agent Service resolution failures ("Error loading your agents"). The
> `post-provision.sh` Step 3 loop performs the spoke links.

**`scaffold-demo.md` — step 4 (ACR build path), add:**

> Before enabling an in-VNet **ACR Tasks agent pool**, confirm
> `Microsoft.ContainerRegistry/registries/agentPools` is available in the target region
> (unavailable in North Central US). If not, set `DEPLOY_ACR_TASK_AGENT_POOL=false` and use
> `az acr build` (cloud Quick Task) or a pool in an adjacent supported region.

**`mcaps-compliance` skill — new "Connectivity troubleshooting (client)" note:**

> On a managed macOS device, if TLS to Azure private endpoints blackholes (~5s) while the
> P2S VPN looks connected and `tcpdump -ni <vpn-utun>` shows no packets, the **Global Secure
> Access** client's **Private Access** profile is intercepting RFC1918 traffic. Disable GSA
> Private Access only (keep Internet Access + M365), then reconnect the Azure VPN
> (`scutil --nc start "<vpn-connection>"`). Smoke-test a private endpoint with
> `curl --resolve <host>:443:<privateIP>` because macOS scoped DNS may otherwise resolve the
> public IP.

---

## Cross-references

- Deployed handles for Phase 2: [`docs/PHASE1-HANDOFF.md`](PHASE1-HANDOFF.md)
- Runbook: [`PROVISION.md`](../PROVISION.md)
- Reproducible env + region flags: [`scripts/configure-azd-env.sh`](../scripts/configure-azd-env.sh)
- Post-deploy wiring (reverse peering + spoke DNS links): [`scripts/post-provision.sh`](../scripts/post-provision.sh)
