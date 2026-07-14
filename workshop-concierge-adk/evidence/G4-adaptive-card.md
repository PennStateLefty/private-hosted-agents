# G4 — Adaptive Card + Callback Correlation — PASS (live Teams delivery is G3)

Proves the Adaptive Card request/response cycle preserves a **single correlation id
end-to-end** across the callback boundary, that the bounded single-alternative rule
holds through card submits, and that acceptance claims **no external commitment** —
all deterministically and reproducibly. The only piece deferred to G3 is the live
Bot Service delivery of these cards into Teams.

## Components

- `src/workshop_concierge/cards.py` — Adaptive Card 1.5 builders (intake +
  recommendation). Every `Action.Submit` embeds `correlation_id` in its `data`.
- `src/workshop_concierge/teams_dispatch.py` — **new** pure callback dispatcher: the
  exact request/response contract a Teams / Bot Service messaging endpoint invokes.
  `handle_submit(data, session)` maps an inbound `Action.Submit` payload to a session
  transition and returns the next card/message, threading the inbound correlation id
  through the session and onto every outbound card action. Correlation resolution
  order: inbound submit → session → freshly minted (`wc-<hex>`), then written back so
  the whole conversation shares one id.

## Correlation chain (verified)

```
intake_card(corr) --Action.Submit{submit_intake, corr}-->
recommendation_card(corr) --Action.Submit{show_alternative, corr}-->
recommendation_card(corr, bounded) --Action.Submit{accept, corr}-->
final message(corr, next_action=enroll_intent:<track>)
```

At each hop, every emitted card's `Action.Submit.data.correlation_id` equals the
original id (asserted via `teams_dispatch.submit_correlation_ids`).

## Tests — `tests/test_teams_dispatch.py` (6) + guardrail/session/agent suite

- Intake card carries the correlation id.
- Full chain (intake → alternative → accept) preserves ONE correlation id on every
  output; recommendation is the deterministic Build track; bounded to a single
  alternative; a 2nd alternative is refused **across the callback boundary**; accept
  yields "no external system has been changed" + `enroll_intent:` next action.
- Correlation survives when only the session holds it; is minted + written back when
  absent everywhere; `start_over` returns intake with the same id; unknown action is a
  correlated error.

Deterministic stability — full suite run **3 consecutive times** (`evidence/g4-suite-3x.txt`):

```
run1: 88 passed
run2: 88 passed
run3: 88 passed
```

## Deferred to G3 (live Teams)

The bicep Bot Service + controlled public ingress that actually delivers these cards
into a Teams client is G3 (`evidence/G3-teams-publish.md`). This gate proves the
card + callback correlation *contract* the bot executes; G3 proves live delivery.

## Reproduce

```
cd workshop-concierge-adk && source .venv/bin/activate
python -m pytest tests/test_teams_dispatch.py -q   # 6 passed
python -m pytest -q                                # 88 passed
```
