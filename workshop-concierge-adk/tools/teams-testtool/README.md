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

## Manifest

The Playground does not process the app manifest, but the repo's
[`../../teams/manifest/manifest.json`](../../teams/manifest/manifest.json) is the same
one used for real publishing; no separate manifest is needed here.

## Files

| File | Purpose |
| --- | --- |
| `host.py` | aiohttp local connector host; reuses `handle_activity`. |
| `run-bot.sh` | Start the host on `:3978`. |
| `run-testtool.sh` | Start the Agents Playground pointed at the host. |
| `smoke.py` | Headless round-trip check against a running host (no browser). |
| `requirements.txt` | Test-only deps (`aiohttp`). Mirrors the `testtool` extra in `pyproject.toml`. |
