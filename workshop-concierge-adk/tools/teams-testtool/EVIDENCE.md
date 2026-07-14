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

`pytest` (offline subset) = **85 passed** — the pre-existing 79 plus the 6 new host tests.
The `test_adapter_contract.py`, `test_adk_runner.py`, `test_agent.py` modules only fail at
*collection* because `google-adk` / `litellm==1.91.1` (Requires-Python `<3.14`) cannot
install on this machine's Python 3.14.6 — a pre-existing environment constraint, unrelated
to this change and unaffected by it.

## Isolation

Additive only under `workshop-concierge-adk/`: `tools/teams-testtool/*`,
`tests/test_testtool_host.py`, and a `testtool` optional-dependency group in
`pyproject.toml`. Nothing touches `landing-zone/`, `infra/`, `azure.yaml`, or azd; the
shipped runtime `dependencies` are unchanged.
