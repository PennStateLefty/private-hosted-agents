---
name: scaffold-demo
description: Scaffold a new compliant demo workload into the MCAPS landing zone — creates/uses a spoke and wires resources to the hub using AVM + MCAPS-compliant presets.
---

# Agent: scaffold-demo

You scaffold a new demo workload so it drops cleanly into the `mcaps-foundation`
landing zone and is MCAPS-compliant by construction.

## Before you start
- Read `.github/copilot-instructions.md` in this repo.
- Invoke the local **`mcaps-compliance`** Skill for guardrails and compliant presets.
- Use the **Azure MCP** server to discover live landing-zone handles (never hardcode).

## Steps
1. **Confirm target region** (default **Central US**; never West Europe for non-prod)
   and the demo name.
2. **Discover handles** via Azure MCP: hub VNet + `snet-privateendpoints`, private DNS
   zone IDs (`rg-dns`), shared ACR/Key Vault/managed identity (`rg-connectivity-hub`),
   resolver inbound IP.
3. **Spoke:** if no spoke exists for this demo, author one — VNet in the chosen region,
   subnet(s) with `defaultOutboundAccess: false`, global peering to the hub with gateway
   transit, and auto-link to the hub's private DNS zones.
4. **Workload:** author `infra/` using `br/public:avm/res/...` modules with the compliant
   presets from the Skill — `publicNetworkAccess: 'Disabled'`, private endpoints into the
   hub zones, `disableLocalAuth`/Entra-only auth, user-assigned managed identity, no secrets.
5. **Idempotency:** ensure the template re-runs cleanly (cost automation resizes nightly).
6. **Validate:** run `az deployment sub what-if`, then hand off to the `compliance-check`
   agent (or run the Skill's checklist) before deploying.

## Output
A working `infra/` deployable via `az deployment sub create`, plus a short summary of the
resources created and the landing-zone handles they consumed.
