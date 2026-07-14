# G1 — Local Responses Adapter + Container + Live Model (D1)

_Captured: 2026-07-10._

## 1. Contract tests (offline, deterministic)

The adapter (`src/adapter/app.py`) hosts the ADK agent behind
`ResponsesAgentServerHost` (Starlette ASGI). Contract tests drive it via
`starlette.testclient.TestClient`:

- `/readiness` returns success (platform auto-probe path).
- Non-streaming `/responses` turn returns a `TextResponse` with the agent reply.
- Non-success requests return the Responses error envelope shape.

`python -m pytest` → **60 passed** (host venv + container). Adapter maps the
Responses `conversation_id` → ADK `session_id`, preserving multi-turn state.

## 2. Container (linux/amd64) — reproducible build & tests

```
docker build --platform linux/amd64 --target test -t workshop-concierge:test .
...
#14 [test 4/4] RUN python -m pytest
#14 ............................................................  [100%]
60 passed, 2 warnings in 2.55s
```

Image manifest digest (multi-arch list, amd64):

```
sha256:2aec0360b231e731e22fd47a54cbbffca28d5b3a110d8065945afea599744f8e
```

Build installs the full freeze with `--no-deps` (see G0 otel note); tests run
in-image, proving the runtime image imports and the agent path work on
linux/amd64 (the Foundry hosted-agent target platform).

## 3. Live model reachability (D1 hard gate) — Foundry model over private path

### 3a. Raw Azure OpenAI call (isolate endpoint + Entra auth + deployment)

```
POST https://aif-zliorc-pha-dev-ncus-001.services.ai.azure.com \
     /openai/deployments/chat/chat/completions?api-version=2025-04-01-preview
Authorization: Bearer <Entra token, scope cognitiveservices.azure.com/.default>

-> HTTP 200
   model  = gpt-5.4-mini-2026-03-17
   content= "pong"
```

Confirms: private endpoint reachable, **Entra-only auth honored**
(`disableLocalAuth=true`), deployment name `chat` valid, api-version good.

### 3b. Full ADK agent -> Foundry model (end-to-end D1)

`scripts/smoke-live.py` runs the **real** `create_agent()` with
`build_foundry_model()` (LiteLLM `azure/chat`, `azure_ad_token_provider` =
`DefaultAzureCredential` bearer) through `ConciergeRunner`:

```
>> turn 1: intake  "I'm a Developer and my goal is to Build an agent."
agent: Recommended: **Build Track**. ...
tool recommendation track_id: build
correlation_id in state: smoke-corr-1

>> turn 2: alternative (continuity) "Show me the alternative track."
agent: Alternative: **Integrate Track**. ...

RESULT: PASS - tool selected track: build
```

Proves the complete hard-feasibility chain **D1**:
ADK `LlmAgent` + `FunctionTool(recommend_track)` + Foundry `gpt-5.4-mini` via
LiteLLM with **Entra auth** over the **private network**, with deterministic
tool selection, correlation-id threading, and bounded single-alternative
continuity across turns.

## Result

G1 = **PASS** (offline contract + linux/amd64 container + live D1 model path).
