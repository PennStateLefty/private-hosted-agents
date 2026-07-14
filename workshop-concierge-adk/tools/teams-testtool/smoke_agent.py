#!/usr/bin/env python3
"""Headless smoke test for the local host in AGENT mode (real ADK agent + Foundry model).

Drives what the Agents Playground would drive through a browser, but headless: stands up
a throwaway fake Bot Framework connector, opens a conversation (expects the agent's
proactive greeting), then sends a real user message and expects a **text** reply produced
by the actual agent (not an Adaptive Card). Because agent mode calls the deployed Foundry
model, this requires the host to be started via ``run-bot-agent.sh`` (py3.13 venv + VPN +
model RBAC).

Usage (with ./run-bot-agent.sh already running in another terminal):

    python smoke_agent.py

Exits non-zero on assertion failure. Prints the agent's reply so you can eyeball that the
model actually narrated a recommendation; the telemetry spans print in the *bot* terminal.
"""
from __future__ import annotations

import asyncio
import os
import sys

from aiohttp import ClientSession, web

BOT = os.environ.get("BOT_URL", "http://localhost:3978")
CONNECTOR_PORT = int(os.environ.get("CONNECTOR_PORT", "3991"))
CONV = os.environ.get("CONV", "smoke-agent-1")
PROMPT = os.environ.get(
    "PROMPT",
    "I'm a software developer and I want to learn to build an AI agent. "
    "Which workshop track should I take?",
)


async def _run() -> int:
    received: list[dict] = []

    async def collect(req: web.Request) -> web.Response:
        received.append(await req.json())
        return web.json_response({"id": f"srv-{len(received)}"})

    app = web.Application()
    app.router.add_post("/v3/conversations/{cid}/activities", collect)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "localhost", CONNECTOR_PORT).start()
    svc = f"http://localhost:{CONNECTOR_PORT}"

    def base(extra: dict) -> dict:
        a = {
            "serviceUrl": svc,
            "channelId": "msteams",
            "conversation": {"id": CONV},
            "recipient": {"id": "bot-1", "name": "Workshop Concierge"},
            "from": {"id": "user-1", "name": "Tester"},
        }
        a.update(extra)
        return a

    try:
        async with ClientSession() as s:
            # 1) conversation open -> agent proactively greets (text, not a card)
            await s.post(f"{BOT}/api/messages", json=base(
                {"type": "conversationUpdate", "id": "a1", "membersAdded": [{"id": "user-1"}]}
            ))
            await asyncio.sleep(0.3)
            greeting = received[-1]
            assert greeting.get("type") == "message" and greeting.get("text"), "no greeting text"
            assert "attachments" not in greeting, "agent mode should reply with text, not a card"
            print(f"✓ agent proactive greeting: {greeting['text'][:80]!r}")

            # 2) real user turn -> real agent + Foundry model -> narrated text reply
            #    (this is the call that emits the teams.turn + tool spans in the bot terminal)
            await s.post(f"{BOT}/api/messages", json=base({
                "type": "message", "id": "a2", "text": PROMPT,
            }))
            # model round-trips can take a few seconds; poll for the reply.
            for _ in range(120):  # up to ~60s
                await asyncio.sleep(0.5)
                if len(received) >= 2:
                    break
            assert len(received) >= 2, "no agent reply within timeout (VPN/model reachable?)"
            reply = received[-1]
            assert reply.get("type") == "message", "expected a message reply"
            text = reply.get("text") or ""
            assert text.strip(), "agent reply text was empty"
            assert not text.startswith("(agent error:"), f"agent errored: {text}"
            corr = (reply.get("channelData") or {}).get("correlationId")
            print(f"✓ agent reply (correlation={corr}):\n---\n{text}\n---")

        print(f"\nPASS — {len(received)} activities delivered; real agent turn completed.")
        return 0
    except AssertionError as exc:
        print(f"\nFAIL — {exc}", file=sys.stderr)
        return 1
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(_run()))
    except ConnectionError:
        print("Could not reach the bot host — is ./run-bot-agent.sh running?", file=sys.stderr)
        raise SystemExit(2)
