# Local Teams App Test Tool harness (LOCAL TEST ONLY — never deployed)

Exercise the Workshop Concierge Teams integration **entirely offline** in the
Microsoft 365 Agents Playground (a.k.a. the Microsoft Teams App Test Tool, "Teams
playground") with:

- **no** M365 tenant or Copilot license,
- **no** Azure Bot registration,
- **no** tunnel (ngrok / Dev Tunnel), and
- **no** Azure connectivity at all (no VPN, no `az login`).

The bot **proactively initiates** the chat (sends the intake Adaptive Card when the
conversation opens), then advances via `Action.Submit`:
`submit_intake → recommendation card → accept`.

> ⚠️ **This is a test-only rig.** In production there is **no custom bot host** — the
> Foundry Hosted Agent serves the Bot Framework `activity` protocol natively (see
> [`../../KNOWN-ISSUES.md`](../../KNOWN-ISSUES.md) #1 and
> [`../../architecture/decisions/ADR-001-teams-public-ingress.md`](../../architecture/decisions/ADR-001-teams-public-ingress.md)).
> Nothing here is wired into `azure.yaml`, `infra/`, or azd, and it must never be.

## What it does

`host.py` is a thin [aiohttp](https://docs.aiohttp.org/) host that speaks the local
Bot Framework connector protocol and **reuses the shipped translation layer unchanged**
— it imports `bot.messaging.handle_activity`, which calls
`workshop_concierge.teams_dispatch` and `workshop_concierge.cards`. No card or dispatch
logic is reimplemented.

```
Agents Playground  --POST /api/messages-->  host.py  --handle_activity()-->  cards/dispatch
        ^                                      |
        |     POST {serviceUrl}/v3/conversations/{id}/activities (reply)
        +--------------------------------------+
```

- `POST /api/messages` — inbound Activity → reply Activity via the connector.
- `POST /api/proactive` — send a *real* proactive message (intake card, or `{"text": …}`)
  to a known conversation with **no** inbound trigger. Proves proactive delivery works.
- `GET /health` — liveness + number of known conversations.

> **Python note:** this host is deliberately raw-aiohttp (not `botbuilder-core`). On
> this machine's Python 3.14 the pinned `botbuilder-core` / `litellm` stack does not
> install, and the Test Tool requires no bot auth, so a minimal connector client is all
> that is needed.

## Run it (2 terminals)

**Terminal 1 — start the bot host** (creates/reuses `../../.venv`, installs `aiohttp`):

```bash
cd workshop-concierge-adk/tools/teams-testtool
./run-bot.sh
# → Bot host → http://localhost:3978/api/messages  (LOCAL TEST ONLY)
```

**Terminal 2 — start the Agents Playground** (downloads the CLI from npm on first run):

```bash
cd workshop-concierge-adk/tools/teams-testtool
./run-testtool.sh
# opens the web chat UI in your browser
```

The Playground defaults its bot endpoint to `http://localhost:3978/api/messages`;
`run-testtool.sh` pins it (and `DEFAULT_CHANNEL_ID=msteams`) via env vars. Requires
Node.js + npm (verified with Node 26 / npm 11).

> **Note — tool rename & config format.** The "Teams App Test Tool" is now **Microsoft
> 365 Agents Playground**. The current CLI uses built-in mock data by default (no config
> file needed) and validates any config against a **new** schema (`.m365agentsplayground.yml`
> with root `tenantId` + a `bot` block + exactly five `users`). The old
> `.teamsapptesttool.yml` schema (`version: v1.0` / `config.botEndpoint`) is now **rejected**
> with `ConfigFileParseError: must have required property 'tenantId'`, so this harness ships
> **no** config file and pins the endpoint via `BOT_ENDPOINT` instead. Only add a
> `.m365agentsplayground.yml` if you need custom Teams context — see
> <https://aka.ms/teams-app-test-tool-config-guide>.

### Try it

1. When the chat opens, the Playground fires a `conversationUpdate` (member added) and
   the bot **proactively** renders the **intake card**.
2. Pick a **role** + **goal**, click **Recommend a track** → the **recommendation card**
   appears.
3. Click **Show alternative** (once) or **Accept recommendation** → a confirmation
   message ("…no external system has been changed."). **Start over** resets to intake.

### Prove a real proactive send (optional)

With both terminals running and the chat open once, from a third shell:

```bash
curl -s -X POST http://localhost:3978/api/proactive \
  -H 'content-type: application/json' -d '{"text":"👋 proactive ping from the host"}'
```

The message appears in the Playground chat without you sending anything. Omit `text` to
proactively push the intake card instead.

### Trigger the agent to proactively open a chat

`POST /api/proactive` lets the **agent initiate** a chat with the user with no inbound
message. Use the `trigger-proactive.sh` helper (or curl it directly):

```bash
# Default opener (agent greeting in agent mode / intake card in dispatch mode):
./trigger-proactive.sh

# Send literal text:
./trigger-proactive.sh "👋 checking in — ready to pick a track?"

# Agent mode: have the REAL agent author the opener (and push the recommendation card):
PROMPT="I'm a developer who wants to build an agent — recommend a track" ./trigger-proactive.sh
```

By default this reuses the most recent conversation the host has seen. To open a chat the
user **hasn't messaged yet** (a true cold start), pass the connector coordinates so the
host can address the conversation without any prior inbound activity:

```bash
CONVERSATION_ID=my-conv SERVICE_URL=http://localhost:56150 ./trigger-proactive.sh "hello!"
```

`/api/proactive` body fields (all optional): `conversationId`, `serviceUrl`, `userId`,
`botId`, `channelId` (cold-start addressing); `prompt` (agent-authored opener, agent mode
only); `text` (literal message). See `host.py:handle_proactive` for the full contract.

> **Note:** the Playground creates a conversation client-side when you open the chat, so
> a message pushed to a conversation the browser hasn't opened won't render there. The
> cold-start path is primarily for headless/CI drivers (e.g. the fake connector in
> `tests/test_testtool_host_agent.py`) that own the connector endpoint.

### Headless smoke test (no browser)

The Playground's card rendering is verified visually in the browser, but the **bot side**
can be checked without one. With `./run-bot.sh` running in another terminal:

```bash
cd workshop-concierge-adk && source .venv/bin/activate
python tools/teams-testtool/smoke.py
```

`smoke.py` stands up a throwaway fake connector and drives the exact Activity shapes the
Playground emits (proactive intake → submit_intake → recommendation → accept → proactive
send), asserting the round trip and correlation id. Exits non-zero on failure — handy for
CI or a quick check on Python 3.14 where the Playground's browser UI isn't available.

> **Note:** `./run-testtool.sh` opens the Playground web UI in a browser; it is an
> interactive developer step. In a headless/CI shell the Playground process starts,
> prints `Listening on 56150`, then exits because it cannot open a browser — use
> `smoke.py` there instead.

## Agent mode — run the REAL agent + deployed Foundry model, with telemetry

Everything above is **dispatch mode**: the host reuses the deterministic
`teams_dispatch` card state machine — no LLM, no network, importable on Python 3.14.
That proves the *Teams plumbing* (cards, proactive, correlation) but does **not** run
the actual agent.

**Agent mode** (`WC_HOST_MODE=agent`) instead drives the real Google ADK agent
(`src/workshop_concierge/agent.py`) locally and calls the model **already deployed in
Foundry** (Azure OpenAI `chat` / gpt-5.4-mini). Every turn is wrapped in a `teams.turn`
span and an OpenTelemetry **console exporter** prints the agent's spans to the terminal,
so you can watch it orchestrate: `invoke_agent → call_llm → execute_tool recommend_track
→ call_llm`. The Teams sim, bot host, and agent all run locally — only the model call
leaves the machine.

```
Agents Playground → host.py (WC_HOST_MODE=agent) → agent_bridge → ConciergeRunner
                                                        → real ADK agent → Foundry model
   console spans:  teams.turn ⊃ invoke_agent ⊃ call_llm / execute_tool recommend_track
```

**Prerequisites** (unlike dispatch mode, agent mode needs Azure):

- **Python 3.13** venv at `../../.venv-agent` (google-adk / litellm do **not** install on
  3.14). Create it once:
  ```bash
  /opt/homebrew/bin/python3.13 -m venv ../../.venv-agent
  ../../.venv-agent/bin/pip install -r requirements-agent.txt
  ```
- **VPN up** + `az login`, with **`Cognitive Services OpenAI User`** on the Foundry
  account (the agent authenticates via `DefaultAzureCredential`).
- Foundry endpoint/deployment values — auto-sourced from the main checkout's azd env
  (`.azure/wc-dev/.env`); override with `WC_AZURE_ENV_FILE` or pre-export
  `AZURE_OPENAI_ENDPOINT` / `MODEL_DEPLOYMENT_NAME` / `AZURE_OPENAI_API_VERSION`.

**Run it (2 terminals):**

```bash
# Terminal 1 — real agent + Foundry model + console telemetry:
cd workshop-concierge-adk/tools/teams-testtool
./run-bot-agent.sh

# Terminal 2 — the same Agents Playground (talks to :3978 either way):
./run-testtool.sh
```

In agent mode the bot **proactively greets** on conversation open (text, agent
initiates), then each message you type is answered by the **real agent in narrated
text**. When the agent recommends a track (its `recommend_track` tool fires), it also
**pushes the shared recommendation Adaptive Card** alongside that text — so the agent
speaks the Activity Protocol with a real card, not just prose (the same card the
deterministic dispatch flow renders). Watch Terminal 1 for the spans.

**Headless check (no browser):**

```bash
cd workshop-concierge-adk && .venv/bin/python tools/teams-testtool/smoke_agent.py
```

`smoke_agent.py` drives a proactive greeting + one real user turn and asserts a non-empty
text reply came back; the spans print in the Terminal‑1 (bot) window.

> **Offline wiring check:** set `WC_MODEL=stub` to build the agent object and prove the
> telemetry wiring without a model call (no VPN needed). A real recommendation still
> requires the live Foundry model.

## Manifest

The Playground does not process the app manifest, but the repo's
[`../../teams/manifest/manifest.json`](../../teams/manifest/manifest.json) is the same
one used for real publishing; no separate manifest is needed here.

## Files

| File | Purpose |
| --- | --- |
| `host.py` | aiohttp local connector host; reuses `handle_activity` (dispatch) or drives the real agent (agent mode). |
| `run-bot.sh` | Start the host on `:3978` in **dispatch** mode (deterministic cards, no Azure). |
| `run-bot-agent.sh` | Start the host on `:3978` in **agent** mode (real ADK agent + Foundry model + console telemetry; needs `.venv-agent` + VPN). |
| `run-testtool.sh` | Start the Agents Playground pointed at the host (same for both modes). |
| `trigger-proactive.sh` | Trigger an agent-initiated proactive open via `POST /api/proactive` (text, agent-authored `prompt`, or a cold-start reference). |
| `smoke.py` | Headless round-trip check of **dispatch** mode against a running host. |
| `smoke_agent.py` | Headless check of **agent** mode (proactive greeting + one real agent turn). |
| `agent_bridge.py` | Lazy bridge to `ConciergeRunner`; wraps each turn in a `teams.turn` span. |
| `telemetry.py` | Idempotent console OpenTelemetry exporter for agent mode. |
| `requirements.txt` | Dispatch-mode deps (`aiohttp`). Mirrors the `testtool` extra in `pyproject.toml`. |
| `requirements-agent.txt` | Agent-mode deps (google-adk / litellm / azure-identity / opentelemetry) for the py3.13 `.venv-agent`. |
