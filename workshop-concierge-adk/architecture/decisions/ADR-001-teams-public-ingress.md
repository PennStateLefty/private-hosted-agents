# ADR-001 — Teams / M365 delivery via App Gateway public ingress to the Foundry agent's native activity protocol

- Status: Accepted (deploy-gated — awaiting MCAPS public-ingress exception + TLS cert)
- Date: 2026-07-12
- Supersedes the "custom bot adapter host" assumption in ADR-000-era G3 notes.

## Context

G3 of the golden path publishes the Workshop Concierge Hosted Agent to Microsoft Teams
and M365 Copilot. Two facts drive the design:

1. **Foundry Hosted Agents natively speak the Bot Framework `activity` protocol.** The
   agent endpoint exposes it directly, alongside `responses`:
   `https://<res>.services.ai.azure.com/api/projects/<proj>/agents/<agent>/endpoint/protocols/activityProtocol`.
   Foundry itself performs the `validate-jwt` (issuer `https://api.botframework.com`) and
   end-user RBAC. **There is no translator/bot web app to build** — an earlier assumption
   in this repo (that `src/bot/messaging.py` must be hosted in front of the agent) was
   wrong. `src/bot/messaging.py` remains only as an offline artifact/unit-test fixture.
   Reference: <https://learn.microsoft.com/azure/foundry/agents/how-to/publish-copilot-virtual-network>

2. **This use case requires public ingress.** The Microsoft Bot Channel Adapters that
   deliver Teams/Copilot messages run outside our network and must reach the agent's
   messaging endpoint over the internet. Our Foundry project is PNA-disabled (private
   endpoint, `192.168.2.30`), so the adapters cannot reach it directly. Per the Foundry
   private-network guide, we need (a) a publicly reachable entry point we control and
   (b) TLS termination that forwards inbound to the agent's private endpoint.

The landing zone default is network isolation (`PUBLIC_INGRESS_ENABLED=false`). Public
ingress here is therefore a **deliberate, sanctioned MCAPS policy exception**, not a
compliance regression.

## Decision

Front the Foundry agent's private endpoint with **Azure Application Gateway v2 + WAF** as
the single public-ingress appliance:

```
Teams / M365 Copilot
   │  Bot Channel Adapter (public MS IP ranges, Bot Framework JWT)
   ▼
Azure Bot Service   (msaAppType=SingleTenant, msaAppId = agent instance_identity.principal_id,
   │                 publicNetworkAccess=Disabled; endpoint = App Gateway FQDN + activityProtocol path)
   ▼
Application Gateway v2 + WAF   (public IP, TLS listener, OWASP 3.2 Prevention)
   │  reverse proxy; backend host-override to services.ai.azure.com; probe activityProtocol path
   ▼
Foundry agent PRIVATE endpoint  (services.ai.azure.com → 192.168.2.30 via privatelink DNS)
   │  Foundry: validate-jwt (api.botframework.com) + end-user RBAC
   ▼
Hosted Agent (workshop-concierge)  → reply back out via smba.trafficmanager.net
```

- **App Gateway backends to the Foundry private endpoint**, not to the Azure Bot resource
  and not to any custom compute. The AGW subnet's VNet is linked to
  `privatelink.services.ai.azure.com` so the backend FQDN resolves to the private IP.
- **TLS**: the listener presents a certificate for the messaging-endpoint hostname. A
  custom domain + Key Vault cert (referenced via the AGW user-assigned identity) is the
  intended production shape; the AGW public-IP FQDN + matching cert is acceptable for a
  demo.
- **Inbound hardening**: NSG restricts 443 to the published Teams Bot Channel Adapter IP
  ranges; WAF in Prevention mode; Foundry still enforces JWT + RBAC. Optionally validate
  the `x-tenant-id` header / JWT at the gateway.
- **Outbound**: allow `smba.trafficmanager.net`, `login.microsoftonline.com`,
  `login.botframework.com` so the agent's replies reach the channel.
- **Auth**: no secrets. The bot's `msaAppId` is the agent principal (SingleTenant); the
  AGW uses a user-assigned identity to read the TLS cert from Key Vault.

The whole path is **deploy-gated behind `PUBLIC_INGRESS_ENABLED=true`**. IaC and scripts
are authored and build-clean, but nothing deploys until the exception and TLS cert exist.

## Alternatives considered

- **Bot Service network isolation only (no public ingress):** keeps everything private but
  cannot deliver Teams messages — the channel adapters are external. Rejected: does not
  meet the requirement.
- **Custom bot web host wrapping `src/bot/messaging.py`:** unnecessary — Foundry serves the
  activity protocol natively. Rejected: adds compute, a new web framework dependency, and
  a JWT/Connector implementation Foundry already provides.
- **Azure Firewall DNAT + separate reverse proxy:** valid (the guide allows a firewall +
  behind-it TLS proxy), but two appliances vs App Gateway's single-appliance TLS+WAF+proxy.
  Rejected for this demo on simplicity; revisit if a central firewall already exists.
- **Front Door:** global anycast + WAF, but Private Link origins to Foundry/Bot are not
  supported for this integration; App Gateway in-VNet reaching the private endpoint is the
  cleaner fit here.

## Consequences

- A public IP exists (attack surface) — mitigated by WAF, NSG source-range restriction,
  and Foundry's JWT/RBAC. Requires the documented MCAPS exception sign-off.
- A TLS certificate must be issued and rotated (Key Vault + AGW identity).
- Tenant-scope publishing needs Microsoft 365 admin approval (unchanged by networking).
- `infra/bot/bot-service.bicep` now uses `SingleTenant` + agent principal + PNA Disabled
  (was `UserAssignedMSI` + PNA Enabled). `scripts/publish-teams.sh` orchestrates the native
  flow; `scripts/{enable-activity-protocol,create-appgw-subnet,publish-m365}.sh` are new.
- G3 stays **BLOCKED-EXTERNAL** until live delivery is proven; the App Gateway path is now
  authored and deploy-gated rather than merely conceptual.
