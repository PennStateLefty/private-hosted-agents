# Evidence — local Teams App Test Tool harness (offline, no tenant/Azure)

Local-only rig under `tools/teams-testtool/` that exercises the Teams integration with
**no** M365 tenant/license, **no** Azure Bot registration, and **no** tunnel. It reuses
the shipped `bot.messaging.handle_activity` → `teams_dispatch` → `cards` chain unchanged;
no card or dispatch logic is reimplemented. Never deployed (see KNOWN-ISSUES #1).

## What was verified (2026-07-14)

**1. Unit tests — `tests/test_testtool_host.py` (6 tests, PASS).**
Offline aiohttp tests against a fake Bot Framework connector prove the host's activity
adaptation: conversation-open `conversationUpdate` → proactive intake card;
`Action.Submit` (`submit_intake`) → recommendation card with the correlation id
preserved across turns; bot-only `membersAdded` is not answered; `/api/proactive`
delivers an untriggered message; `/api/proactive` with no known conversation → 409;
`/health` → 200.

**2. Live host round trip — `tools/teams-testtool/smoke.py` (PASS).**
Against a running `./run-bot.sh` (`http://localhost:3978/api/messages`), a throwaway fake
connector received the full sequence:

```
✓ proactive intake card  (correlation=wc-309ee1fcb8b5)
✓ recommendation card    (Build Track — ADK to Responses on Foundry Hosted Agents)
✓ accept confirmation     (nextAction=enroll_intent:build)
✓ real proactive message
PASS — 4 activities delivered through the connector.
```

Host access log confirmed 4 outbound deliveries to
`/v3/conversations/<id>/activities [200]` plus the `POST /api/proactive` path.

**3. Agents Playground CLI launches and targets the bot.**
`npx @microsoft/teams-app-test-tool@latest start` (via `./run-testtool.sh`) started and
printed `Listening on 56150`, reading `.teamsapptesttool.yml`
(`botEndpoint: http://localhost:3978/api/messages`). The interactive Adaptive Card
render + `Action.Submit` click-through is a **browser** step (open `http://localhost:56150`);
in a headless shell the Playground exits after startup because it cannot open a browser —
`smoke.py` covers that path non-visually.

## Regression

`pytest` (offline subset) = **87 passed** — the pre-existing 79, the 6 host tests, plus 2
new offline agent-mode tests (greeting / empty-message paths of `_agent_outbound`, which
don't need google-adk). The `test_adapter_contract.py`, `test_adk_runner.py`,
`test_agent.py` modules only fail at *collection* because `google-adk` /
`litellm==1.91.1` (Requires-Python `<3.14`) cannot install on this machine's Python
3.14.6 — a pre-existing environment constraint, unrelated to this change and unaffected
by it.

## Agent mode — real ADK agent + deployed Foundry model + telemetry (2026-07-14)

`WC_HOST_MODE=agent` drives the **actual** `src/workshop_concierge/agent.py` ADK agent
locally (py3.13 `.venv-agent`) and calls the model **already deployed in Foundry**
(`AZURE_OPENAI_ENDPOINT=…aif-zliorc-pha-dev-ncus-001…`, deployment `chat`) over the P2S
VPN via `DefaultAzureCredential`. A console OpenTelemetry exporter (`telemetry.py`) prints
the spans; each turn is wrapped in a `teams.turn` span (`agent_bridge.py`).

**Live headless run — `tools/teams-testtool/smoke_agent.py` (PASS)** against
`./run-bot-agent.sh`:

```
✓ agent proactive greeting: "👋 Hi, I'm the Workshop Concierge. Tell me about your goals…"
✓ agent reply (correlation=wc-50317fa1c9d1):
---
Take the **Build Track — ADK to Responses on Foundry Hosted Agents**.
It fits a **developer** whose primary goal is to **build an agent**.
If you want, I can also share the single alternative track.
---
PASS — 2 activities delivered; real agent turn completed.
```

That reply text was produced by the live Foundry model (not the deterministic dispatch
path). The console spans emitted for the turn, in order:

```
execute_tool recommend_track
generate_content azure/chat
call_llm
generate_content azure/chat
call_llm
invoke_agent workshop_concierge
invocation
teams.turn
```

i.e. `invocation → invoke_agent → call_llm (decide) → execute_tool recommend_track →
call_llm (narrate)`, all inside our `teams.turn`. Key attributes captured on the spans:

```json
// execute_tool recommend_track
"workshop.tool.name": "recommend_track",
"workshop.recommended_track": "build",
"workshop.correlation_id": "wc-50317fa1c9d1",
"gcp.vertex.agent.tool_call_args": "{\"role\": \"Developer\", \"goal\": \"Build an agent\"}"
// teams.turn
"teams.conversation_id": "smoke-agent-1", "teams.input_chars": 102, "teams.output_chars": 201
```

This proves the real agent orchestrates the response and the tool spans `agent.py`
emits (`workshop.*`) surface locally — the same signals the Foundry Hosted Agent runtime
would export in production. Agent mode is import-isolated (lazy) so dispatch mode still
imports on Python 3.14; `host.py` verified importable under both the 3.14 `.venv`
(dispatch) and the 3.13 `.venv-agent` (agent).

## Isolation

Additive only under `workshop-concierge-adk/`: `tools/teams-testtool/*`,
`tests/test_testtool_host.py`, and a `testtool` optional-dependency group in
`pyproject.toml`. Nothing touches `landing-zone/`, `infra/`, `azure.yaml`, or azd; the
shipped runtime `dependencies` are unchanged.
