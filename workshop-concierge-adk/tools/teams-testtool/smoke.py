#!/usr/bin/env python3
"""Headless smoke test for the local Teams Test Tool host (no browser required).

Drives the full conversation the Agents Playground would drive through a browser —
proactive intake card → submit_intake → recommendation → accept → real proactive send —
by standing up a throwaway fake Bot Framework connector and posting the same Activity
shapes the Playground emits to the running host at http://localhost:3978/api/messages.

Usage (with ./run-bot.sh already running in another terminal):

    python smoke.py            # or: ./smoke.py

Exits non-zero on any assertion failure. This is a convenience for headless/CI checks;
the interactive card rendering is verified visually via ./run-testtool.sh in a browser.
"""
from __future__ import annotations

import asyncio
import os
import sys

from aiohttp import ClientSession, web

BOT = os.environ.get("BOT_URL", "http://localhost:3978")
CONNECTOR_PORT = int(os.environ.get("CONNECTOR_PORT", "3990"))
CONV = "smoke-conv-1"


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
            "channelId": "emulator",
            "conversation": {"id": CONV},
            "recipient": {"id": "bot-1", "name": "Workshop Concierge"},
            "from": {"id": "user-1", "name": "Tester"},
        }
        a.update(extra)
        return a

    try:
        async with ClientSession() as s:
            # 1) conversation open -> proactive intake card
            await s.post(f"{BOT}/api/messages", json=base(
                {"type": "conversationUpdate", "id": "a1", "membersAdded": [{"id": "user-1"}]}
            ))
            await asyncio.sleep(0.15)
            card = received[-1]["attachments"][0]["content"]
            assert card["type"] == "AdaptiveCard", "expected intake AdaptiveCard"
            corr = card["actions"][0]["data"]["correlation_id"]
            print(f"✓ proactive intake card  (correlation={corr})")

            # 2) submit_intake -> recommendation card, correlation preserved
            await s.post(f"{BOT}/api/messages", json=base({
                "type": "message", "id": "a2",
                "value": {"action": "submit_intake", "role": "Developer",
                          "goal": "Build an agent", "correlation_id": corr},
            }))
            await asyncio.sleep(0.15)
            rec = received[-1]
            assert rec["attachments"][0]["content"]["type"] == "AdaptiveCard"
            assert rec["channelData"]["correlationId"] == corr, "correlation id drifted"
            print(f"✓ recommendation card    ({rec['attachments'][0]['content']['body'][1]['text']})")

            # 3) accept -> confirmation, no external commitment
            await s.post(f"{BOT}/api/messages", json=base({
                "type": "message", "id": "a3",
                "value": {"action": "accept", "correlation_id": corr},
            }))
            await asyncio.sleep(0.15)
            final = received[-1]
            assert "no external system has been changed" in final["text"].lower()
            assert final["channelData"]["nextAction"].startswith("enroll_intent:")
            print(f"✓ accept confirmation     (nextAction={final['channelData']['nextAction']})")

            # 4) real proactive send (no inbound trigger)
            r = await s.post(f"{BOT}/api/proactive", json={"conversationId": CONV, "text": "ping"})
            assert r.status == 200
            await asyncio.sleep(0.15)
            assert received[-1]["text"] == "ping"
            print("✓ real proactive message")

        print(f"\nPASS — {len(received)} activities delivered through the connector.")
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
        print("Could not reach the bot host — is ./run-bot.sh running?", file=sys.stderr)
        raise SystemExit(2)
