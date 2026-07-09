# AGENTS.md

Guidance for AI agents working in this demo repo. This repo deploys into the
**MCAPS `mcaps-foundation` landing zone** (hub-and-spoke, single MCAP-managed
subscription) and must be **MCAPS-compliant by default**.

## Start here
1. Read [`.github/copilot-instructions.md`](.github/copilot-instructions.md) — the full
   landing-zone context and golden rules.
2. Invoke the local **`mcaps-compliance`** Copilot Skill for policy guardrails and
   compliant-by-default presets. Never paste MCAPS catalog text into this repo.
3. Use the **Azure MCP** server to discover live landing-zone handles at runtime —
   never hardcode resource IDs, subscription IDs, or secrets.

## Non-negotiables
- Build on **Azure Verified Modules** (`br/public:avm/res/...`), pinned + Renovate-managed.
- `publicNetworkAccess: 'Disabled'` + private endpoints into the hub's `privatelink.*` zones.
- Entra/managed-identity auth only — no keys, connection strings, SAS, or pinned certs.
- Subnets set `defaultOutboundAccess: false`.
- Idempotent/redeployable (nightly cost automation resizes/deallocates resources).
- Approved region only (default **Central US**; never West Europe for non-prod).

## Purpose-built agents
- `scaffold-demo` — stamp a compliant workload/spoke wired to the hub.
- `compliance-check` — check IaC / what-if against MCAPS controls before deploy.
