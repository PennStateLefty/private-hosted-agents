# mcaps-demo-template

A **GitHub template repository** for building demos that deploy into the MCAPS
`mcaps-foundation` Azure landing zone (hub-and-spoke, single MCAP-managed subscription).
Click **"Use this template"** to stamp a new demo repo.

Each demo is its own repo with its own IaC, but must fit the landing zone's topology and
be **MCAPS-compliant by default**. This template wires a fresh GitHub Copilot session
(CLI / GitHub App / VS Code) to everything it needs to do that with minimal friction.

## What you get

| File | Purpose |
| --- | --- |
| [`.github/copilot-instructions.md`](.github/copilot-instructions.md) | Landing-zone context + golden rules for any Copilot session |
| [`AGENTS.md`](AGENTS.md) | Same guidance, in the portable AGENTS.md format |
| [`.github/agents/scaffold-demo.md`](.github/agents/scaffold-demo.md) | Agent that stamps a compliant workload/spoke |
| [`.github/agents/compliance-check.md`](.github/agents/compliance-check.md) | Agent that checks IaC/what-if against MCAPS controls |
| [`infra/`](infra/) | Thin AVM-based Bicep skeleton with compliant presets |
| [`renovate.json`](renovate.json) | Keeps AVM module versions current |

## Two dependencies you provide (not shipped here)

1. **The `mcaps-compliance` Copilot Skill** — installed locally (`~/.copilot/skills/`).
   It carries the confidential MCAPS policy guardrails and compliant presets. This repo
   only *references* it by name; the raw catalogs never live in a shareable repo.
2. **The Azure MCP server** — for discovering live landing-zone handles (resource IDs,
   ACR login server, DNS zone IDs, resolver IP) at runtime. Nothing volatile is hardcoded.

## Stamp-out flow

1. "Use this template" → create your demo repo.
2. Open it with Copilot; it reads `.github/copilot-instructions.md` / `AGENTS.md`.
3. Ask the `scaffold-demo` agent to build your workload (it uses the Skill + Azure MCP).
4. Run `compliance-check` on the what-if, then deploy.

## Why this stays fresh

The template embeds **references** — the Skill name, AVM module refs, and discovery
instructions — not copies of volatile state. Live handles come from Azure MCP; policy
comes from the locally-updated Skill; module versions are bumped by Renovate. New demos
pick up the latest by construction.

## This demo: private hosted agents (Phase 1 infrastructure)

This repo is being used to test the new C# **Foundry hosted agents** against a private,
MCAPS-compliant environment. **Phase 1 = infrastructure** (private Foundry + Agent Service
spoke + optional APIM AI Gateway). See **[`PROVISION.md`](PROVISION.md)** for the full runbook.

| Path | Purpose |
| --- | --- |
| [`landing-zone/`](landing-zone/) | Vendored `troyhite/bicep-ptn-aiml-landing-zone` (pinned) — the private Foundry/Agent-Service spoke, run via `azd` in `ailz-integrated` mode |
| [`scripts/configure-azd-env.sh`](scripts/configure-azd-env.sh) | Sets every `azd` env var for the `mcaps-foundation` hub |
| [`scripts/prep-hub-dns.sh`](scripts/prep-hub-dns.sh) | Pre-creates + hub-links the missing privatelink DNS zones |
| [`scripts/post-provision.sh`](scripts/post-provision.sh) | Reverse hub→spoke peering (gateway transit) + hub-links spoke DNS zones |
| [`infra/`](infra/) | Additive **APIM GenAI gateway** in front of the Foundry account |

Non-production scope: a compliance + private-network **simulation** (single hub, cross-region
spoke), not a production topology.
