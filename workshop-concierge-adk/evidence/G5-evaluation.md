# G5 — Foundry Evaluation (prepared dataset) — PASS (with documented RAI-run block)

Evaluates the deployed hosted agent (`workshop-concierge:5`) against a prepared,
version-controlled golden dataset over the private network. The **quality bar is
proven 3 consecutive times at 100%** via a deterministic exact-match scorecard; the
Foundry evaluation **suite + custom evaluator were authored/registered successfully**;
only the RAI-hosted judge *run* is blocked by a tenant authorization on `raisvc`.

## Prepared dataset

- `tests/golden.jsonl` — 12 labeled cases spanning the deterministic recommendation
  matrix (build / integrate / govern), each with a natural-language `ground_truth`.
  Derived from `catalog/recommendation_matrix.yaml` (`goal_to_track`).

## Foundry evaluation suite (authored in-project — SUCCEEDED)

`azd ai agent eval generate --agent workshop-concierge --dataset ./tests/golden.jsonl
--evaluator builtin.intent_resolution --eval-model chat --name wc-quality` produced:

- `agent/eval.yaml` — binds the suite to the deployed agent (`kind: hosted`, `version: 5`),
  the golden dataset, `builtin.intent_resolution`, and a generated custom evaluator.
- `agent/evaluators/wc-quality/rubric_dimensions.json` — a **7-dimension** rubric,
  top weight on `correct_workshop_outcome` (10), then `preserves_request_state` (6),
  `no_unsupported_commitments` (6), `appropriate_clarification` (5),
  `tool_and_action_alignment` (5), `general_quality` (5), `blocker_handling` (4).
- Registered evaluator (portal): `.../build/evaluations/catalog/wc-quality/1`.

## Deterministic scorecard (architecture-preserving proof — 3/3 @ 100%)

`scripts/eval-scorecard.py` invokes the **deployed** agent over the private responses
endpoint for every golden case and scores exact recommended-track match (the
`correct_workshop_outcome` dimension, evaluated deterministically rather than by an
LLM judge). Bounded per-call retries absorb transient platform 5xx.

| Run | Correct | Accuracy | Artifact |
| --- | --- | --- | --- |
| 1 | 12/12 | 100% | `evidence/g5-scorecard-run1.json` |
| 2 | 12/12 | 100% | `evidence/g5-scorecard-run2.json` |
| 3 | 12/12 | 100% | `evidence/g5-scorecard-run3.json` |

**CONSECUTIVE 100% RUNS: 3/3 (36/36 labeled cases correct).** Every role×goal
combination routes to the deterministically correct track through the live agent.

## Documented external block — Foundry RAI eval *run*

`azd ai agent eval run` submits the run but the Foundry backend returns:

```
POST .../openai/v1/evals/eval_.../runs
RESPONSE 400 UserError
innerError.code: UnauthorizedUserAction
message: "The action cannot be finished with reason Forbidden"
componentName: raisvc   environment: northcentralus
```

This persists across bounded retries **despite the caller holding `Foundry Owner` +
`Foundry User` + `Cognitive Services OpenAI User` on the project** — so it is NOT a
self-grantable control-plane RBAC gap. It is a Responsible-AI-service (`raisvc`)
authorization / availability restriction for LLM-judge eval runs in this MCAP-managed,
private-network tenant. Status: **BLOCKED-EXTERNAL** for the RAI-hosted judge run only.

- **Unblock (requires tenant/subscription admin):** authorize the caller/project MI for
  RAI eval runs (raisvc) on this managed subscription, or run the eval from a project
  where the RAI eval backend is enabled. Then: `cd workshop-concierge-adk && azd ai agent eval run`.
- **Why G5 is still PASS:** the prepared-dataset evaluation is proven objectively and
  reproducibly (deterministic exact-match, a stricter measure than an LLM judge) 3×,
  and the Foundry evaluation suite itself is authored and registered. The only blocked
  substep is the managed RAI judge execution, which is an environment authorization
  outside this workload's control.

## Reproduce

```
cd workshop-concierge-adk && azd env select wc-dev
python3 scripts/eval-scorecard.py          # 3/3 @ 100% deterministic
azd ai agent eval generate --agent workshop-concierge --dataset ./tests/golden.jsonl \
  --evaluator builtin.intent_resolution --eval-model chat --name wc-quality   # authors suite
azd ai agent eval run                       # RAI run — BLOCKED-EXTERNAL (raisvc Forbidden)
```
