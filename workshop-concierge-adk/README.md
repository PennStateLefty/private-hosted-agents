# Workshop Concierge — ADK agent on a private Foundry Hosted Agent

A **Google ADK** agent that recommends a workshop track (build / integrate / govern)
from a short intake, adapted to the **Microsoft Foundry Hosted Agent** Responses
protocol and fronted by a **Microsoft Teams** integration (Adaptive Cards + proactive
messaging over the Bot Framework Activity Protocol).

It runs three ways:

| Mode | LLM? | Azure? | Use it to… |
| --- | --- | --- | --- |
| **Dispatch** (local) | No | No | Demo the Teams card UX + proactive send deterministically — never fails. |
| **Agent** (local) | **Yes** (deployed Foundry model) | VPN + `az login` | Demo the **real agent** narrating a recommendation and pushing a card, with live telemetry. |
| **Deployed** | Yes | Full landing zone | The production Foundry Hosted Agent (Entra-only, private endpoints). See `DEMO-SCRIPT.md`. |

> This README is the **local run** guide — everything you need to demo the agent on a
> laptop. For the deployed golden path and architecture, see
> [`FINAL-REPORT.md`](FINAL-REPORT.md) and [`DEMO-SCRIPT.md`](DEMO-SCRIPT.md).

---

## Table of contents

- [What you can demo](#what-you-can-demo)
- [Prerequisites](#prerequisites)
- [Quick start — Dispatch mode (no Azure)](#quick-start--dispatch-mode-no-azure)
- [Quick start — Agent mode (live Foundry LLM)](#quick-start--agent-mode-live-foundry-llm)
- [Proactively open a chat](#proactively-open-a-chat)
- [Headless smoke tests (no browser)](#headless-smoke-tests-no-browser)
- [Run the test suite](#run-the-test-suite)
- [Repository layout](#repository-layout)
- [Troubleshooting](#troubleshooting)
- [Further reading](#further-reading)

---

## What you can demo

1. **Adaptive Cards over the Activity Protocol.** In both local modes the agent renders
   the shared **intake** and **recommendation** Adaptive Cards. In agent mode the *real*
   ADK agent pushes the recommendation card alongside its narrated answer whenever its
   `recommend_track` tool fires.
2. **Proactive open.** The agent can initiate the chat with no inbound message — a
   greeting/intake card on conversation open, or an on-demand push via
   `trigger-proactive.sh`.
3. **Live orchestration telemetry.** Agent mode streams OpenTelemetry spans to the
   terminal (`teams.turn ⊃ invoke_agent ⊃ call_llm / execute_tool recommend_track`).

The local Teams harness lives in [`tools/teams-testtool/`](tools/teams-testtool/) and is
**test-only — never deployed** (the deployed Foundry Hosted Agent serves the Activity
protocol natively; see [`KNOWN-ISSUES.md`](KNOWN-ISSUES.md) #1).

---

## Prerequisites

**Both modes**

- **Python 3.13** (`google-adk` / `litellm` do **not** install on 3.14).
  Verify: `python3.13 --version`.
- **Node.js + npm** — only for the browser chat UI (Microsoft 365 Agents Playground).
  Verified with Node 26 / npm 11. Not needed for the headless smoke tests.

**Agent mode only (live model)**

- **Azure P2S VPN connected** and **GSA Private Access disabled** (keep Internet Access +
  M365). This is what makes the private Foundry endpoint resolve to its private IP.
- `az login`, with the role **`Cognitive Services OpenAI User`** on the Foundry account
  (the agent authenticates via `DefaultAzureCredential`).
- Foundry endpoint/deployment values. Agent mode auto-sources these from the azd env
  (`.azure/<env>/.env`); you can override the file with `WC_AZURE_ENV_FILE` or pre-export
  them (see [Agent mode](#quick-start--agent-mode-live-foundry-llm)).

### One-time setup

```bash
cd workshop-concierge-adk

# Python 3.13 virtualenv with the full runtime + dev + harness deps:
python3.13 -m venv .venv
.venv/bin/pip install -e '.[dev,testtool,agent-testtool]'
```

That single venv drives **both** local modes and the tests. (The agent-mode launch
script defaults to a separate `.venv-agent`, but you can point it at this `.venv` with
`WC_AGENT_VENV` — shown below.)

---

## Quick start — Dispatch mode (no Azure)

Deterministic cards, no LLM, no network — the bulletproof demo. **Two terminals**, both
in `tools/teams-testtool/`:

```bash
# Terminal 1 — start the local bot host on :3978
cd workshop-concierge-adk/tools/teams-testtool
./run-bot.sh

# Terminal 2 — start the Agents Playground (opens the chat UI in your browser)
cd workshop-concierge-adk/tools/teams-testtool
./run-testtool.sh
```

In the browser: the chat opens → the bot **proactively renders the intake card** → pick a
**Role** + **Goal** → **Recommend a track** shows the recommendation card → **Show
alternative** (once) or **Accept**. **Start over** resets to intake.

---

## Quick start — Agent mode (live Foundry LLM)

The **real** ADK agent runs locally and calls the model **already deployed in Foundry**;
only the model call leaves the machine. Spans print to the bot terminal.

```bash
# Terminal 1 — real agent + live Foundry model + console telemetry, on :3978
cd workshop-concierge-adk/tools/teams-testtool
WC_AGENT_VENV="$PWD/../../.venv" ./run-bot-agent.sh

# Terminal 2 — the SAME Playground (it always talks to :3978)
cd workshop-concierge-adk/tools/teams-testtool
./run-testtool.sh
```

Notes:

- **`WC_AGENT_VENV="$PWD/../../.venv"`** reuses the Python 3.13 venv you created above, so
  you don't need a separate `.venv-agent`.
- The script defaults to **`BOT_PORT=3978`** — the same port the Playground uses — so run
  agent mode *instead of* dispatch mode (stop the dispatch host first). Don't run both.
- **Foundry env:** the script sources `AZURE_OPENAI_ENDPOINT`, `MODEL_DEPLOYMENT_NAME`,
  `AZURE_OPENAI_API_VERSION`, and `FOUNDRY_PROJECT_ENDPOINT` from the azd env file. If
  your azd env lives elsewhere, set `WC_AZURE_ENV_FILE=/path/to/.env`, or pre-export the
  four vars before launching.

In the browser: the agent **proactively greets** on open, then type e.g. *"I'm a
developer who wants to build an agent"* — the agent narrates a recommendation **and pushes
the recommendation Adaptive Card**. Watch Terminal 1 for the live spans.

---

## Proactively open a chat

With a host running (either mode) and the chat open once in the browser, from a **third**
terminal in `tools/teams-testtool/`:

```bash
# Default opener (agent greeting in agent mode / intake card in dispatch mode):
./trigger-proactive.sh

# Literal text:
./trigger-proactive.sh "👋 checking in — ready to pick a track?"

# Agent mode: have the REAL agent author the opener AND push the recommendation card:
PROMPT="I'm an architect who wants to integrate an agent" ./trigger-proactive.sh
```

The message/card appears with **no user input** — the agent reaching out.

> **Caveat:** the Playground creates a conversation client-side, so **open the chat first,
> then trigger** (warm proactive). The cold-start form (`CONVERSATION_ID=… SERVICE_URL=…
> ./trigger-proactive.sh`) is for headless/CI drivers that own the connector endpoint —
> see [`tools/teams-testtool/README.md`](tools/teams-testtool/README.md).

---

## Headless smoke tests (no browser)

Projector-friendly proofs that drive the exact Activity shapes the Playground emits.
Start the matching host first, then:

```bash
cd workshop-concierge-adk

# Dispatch mode (needs ./run-bot.sh running):
.venv/bin/python tools/teams-testtool/smoke.py

# Agent mode / live LLM (needs ./run-bot-agent.sh running):
.venv/bin/python tools/teams-testtool/smoke_agent.py
```

Each exits non-zero on failure. `smoke_agent.py` asserts a real agent turn came back and
(when the agent recommends) that the recommendation card was pushed.

---

## Run the test suite

```bash
cd workshop-concierge-adk
.venv/bin/python -m pytest
```

The suite is fully offline (fake LLM + fake connector) and covers the adapter contract,
card/dispatch correlation, guardrail, and the local Teams harness.

---

## Repository layout

```
workshop-concierge-adk/
├── src/
│   ├── workshop_concierge/     # the agent: agent.py, recommend.py, cards.py,
│   │                           #   teams_dispatch.py, guardrail.py, catalog.py, session.py
│   ├── adapter/                # Foundry Responses-protocol adapter (adk_runner.py, app.py)
│   └── bot/                    # Bot Framework Activity translation (messaging.py)
├── tools/teams-testtool/       # LOCAL, TEST-ONLY Teams harness (dispatch + agent modes)
├── catalog/                    # workshop track catalog (data)
├── tests/                      # offline test suite
├── scripts/                    # deployed-agent proofs (eval / guardrail / gateway / capstone)
├── infra/ , azure.yaml         # azd + Foundry deployment (see DEMO-SCRIPT.md)
├── teams/manifest/             # Teams app manifest (used for real publishing)
├── DEMO-SCRIPT.md              # ~10-min live demo of the DEPLOYED golden path
├── FINAL-REPORT.md             # architecture + gate status (what's built and proven)
└── KNOWN-ISSUES.md             # external blockers + caveats
```

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `pip install` fails on `google-adk` / `litellm` | You're on Python 3.14. Use **3.13** (`python3.13 -m venv .venv`). |
| Playground starts, prints `Listening on 56150`, then exits | You're in a headless shell — it needs a browser. Use `smoke.py` / `smoke_agent.py` instead. |
| Agent mode: `AuthenticationError` / 401 / 403 from the model | VPN down, not `az login`'d, or missing **`Cognitive Services OpenAI User`** on the Foundry account. |
| Agent mode: endpoint won't resolve / TLS hangs | GSA Private Access is intercepting private IPs — **disable GSA Private Access**, keep the VPN connected. |
| Agent mode: `no AZURE_OPENAI_ENDPOINT set` | Point `WC_AZURE_ENV_FILE` at your azd `.env`, or pre-export the four `AZURE_OPENAI_*` / `FOUNDRY_PROJECT_ENDPOINT` vars. |
| Port 3978 already in use | Stop the other host: `lsof -ti tcp:3978` → `kill <PID>`. Don't run dispatch + agent at once. |
| `./run-testtool.sh`: command not found (npm) | Install Node.js + npm (Node 26 / npm 11 verified). |

More detail and the full `/api/proactive` contract:
[`tools/teams-testtool/README.md`](tools/teams-testtool/README.md).

---

## Further reading

- [`tools/teams-testtool/README.md`](tools/teams-testtool/README.md) — deep dive on the
  local harness (both modes, proactive contract, manifest).
- [`DEMO-SCRIPT.md`](DEMO-SCRIPT.md) — ~10-minute live demo of the **deployed** private
  golden path (routing, guardrail, APIM gateway).
- [`FINAL-REPORT.md`](FINAL-REPORT.md) — architecture as built + gate-by-gate status.
- [`KNOWN-ISSUES.md`](KNOWN-ISSUES.md) — external blockers and environment caveats.
