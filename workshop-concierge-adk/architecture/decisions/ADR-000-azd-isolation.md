# ADR-000: Isolate the agent azd project from the infrastructure azd project

Status: Accepted · 2026-07-10

## Context

The repository already contains an **infrastructure** azd project at
`landing-zone/azure.yaml`:

- `name: azure-ai-lz`
- infra provider `bicep`, module `main`
- active azd environment `pha-dev` under `landing-zone/.azure/pha-dev/` holding the
  provisioned Phase-1 private Foundry landing zone state.

We now need a **second** azd workflow to `azd init` / `azd package` / `azd deploy` the
net-new Workshop Concierge **Foundry Hosted Agent**. Running `azd` for the agent must not
disturb or collide with the landing-zone project or its `pha-dev` environment.

## How azd resolves a project

`azd` locates its project by searching for the **nearest `azure.yaml` walking upward**
from the current working directory. It never searches downward into sibling/child
folders. Each project keeps its own `.azure/` directory (environments, `config.json`,
`.env`) next to its `azure.yaml`.

Consequences:

- The repo root has **no** `azure.yaml`. Running `azd` at the root would find nothing
  (safe — no accidental infra operation), and `azd` in `landing-zone/` continues to
  target the infra project only.
- If the agent `azure.yaml` were placed at the repo root, then `azd` run anywhere under
  the repo (including inside `landing-zone/` if that file were removed) could ambiguously
  resolve — and, more importantly, the agent and infra would share nothing but proximity
  and could confuse operators.

## Decision

Give the agent its **own self-contained azd project** rooted at
`workshop-concierge-adk/azure.yaml`, with its **own** `workshop-concierge-adk/.azure/`
environment (proposed env name `wc-dev`, distinct from infra `pha-dev`).

- All `azd` commands for the agent are run **from inside `workshop-concierge-adk/`**.
- All `azd` commands for infrastructure are run **from inside `landing-zone/`**.
- The two projects share **no** `azure.yaml`, `.azure/` directory, or environment name.
- The agent project consumes landing-zone outputs (Foundry project endpoint, model
  deployment, VNet/subnet IDs, ACR) as **azd env values / parameters**, discovered at
  runtime (`azd env get-values` in `landing-zone/`, or Azure MCP / `az` lookups). None are
  hardcoded.

## Guardrails

- Never run `azd init` at the repo root (it could scaffold a conflicting root
  `azure.yaml`). Always `cd workshop-concierge-adk/` first.
- Never reuse the `pha-dev` environment name for the agent.
- Never run `azd down` from `workshop-concierge-adk/` expecting it to affect
  infrastructure, and never run it against `pha-dev`.
- The agent project targets the **existing** resource group `rg-pha-dev` and the
  **existing** Foundry project; it provisions only the hosted agent (and, if used, its
  own additive resources), not the landing zone.

## Result

Two independent azd projects coexist in one repo with zero shared azd state:

```
private-hosted-agents/
  landing-zone/azure.yaml        # infra project  (env: pha-dev)
  landing-zone/.azure/pha-dev/   # infra env state
  workshop-concierge-adk/azure.yaml   # agent project (env: wc-dev)
  workshop-concierge-adk/.azure/      # agent env state (gitignored)
```
