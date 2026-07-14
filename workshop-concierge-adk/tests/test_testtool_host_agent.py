"""Agent-mode host tests: real ADK agent (scripted FakeLlm) → Adaptive Card + proactive.

Exercises the parts of ``tools/teams-testtool/host.py`` + ``agent_bridge.py`` that drive
the REAL Google ADK agent, but with the offline scripted :class:`FakeLlm` (no network),
proving:

* when the agent recommends a track, the outbound Activity carries the shared
  recommendation Adaptive Card **and** the narrated text (agent speaks the Activity
  Protocol with a card, not just prose),
* the card is pushed only on the turn the recommendation changes (no duplicate cards),
* ``POST /api/proactive`` can open a chat with a body-supplied conversation reference
  (cold start) and, with a ``prompt`` in agent mode, have the agent author the opener.

Skipped cleanly where google-adk / aiohttp aren't installed (e.g. the Python 3.14
offline subset), matching ``test_adk_runner.py``.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("aiohttp")
pytest.importorskip("google.adk")

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from adapter.adk_runner import ConciergeRunner  # noqa: E402
from fakes import FakeLlm  # noqa: E402

ADAPTIVE_CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"

_TOOL_DIR = Path(__file__).resolve().parents[1] / "tools" / "teams-testtool"
if str(_TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOL_DIR))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"tt_{name}", _TOOL_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"tt_{name}"] = mod
    # host imports ``agent_bridge`` by bare name; agent_bridge imports ``telemetry`` by
    # bare name — register both under their bare names so the lazy imports resolve.
    sys.modules.setdefault(name, mod)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


host = _load("host")
agent_bridge = _load("agent_bridge")


@pytest.fixture
def agent_host():
    """Enable agent mode with a FakeLlm-backed runner; isolate host globals."""
    host._AGENT_MODE = True
    agent_bridge._runner = ConciergeRunner(model=FakeLlm(model="fake"))
    host._CORR.clear()
    host._REFERENCES.clear()
    try:
        yield host
    finally:
        host._AGENT_MODE = False
        agent_bridge._runner = None
        host._CORR.clear()
        host._REFERENCES.clear()


async def test_agent_recommendation_pushes_adaptive_card(agent_host):
    activity = {
        "type": "message",
        "text": "I'm a Developer and I want to Build an agent",
        "conversation": {"id": "conv-agent-card"},
    }
    out = await agent_host._agent_outbound(activity, "conv-agent-card")
    assert out is not None
    # Narrated text is preserved…
    assert out["type"] == "message" and out["text"].strip()
    # …and the recommendation Adaptive Card rides alongside it.
    att = out["attachments"][0]
    assert att["contentType"] == ADAPTIVE_CARD_CONTENT_TYPE
    assert att["content"]["type"] == "AdaptiveCard"
    # Correlation id is threaded onto the outbound channelData and the card actions.
    corr = out["channelData"]["correlationId"]
    assert any(
        (a.get("data") or {}).get("correlation_id") == corr
        for a in att["content"]["actions"]
    )


async def test_card_pushed_only_when_recommendation_changes(agent_host):
    activity = {
        "type": "message",
        "text": "I'm a Developer and I want to Build an agent",
        "conversation": {"id": "conv-agent-dup"},
    }
    first = await agent_host._agent_outbound(activity, "conv-agent-dup")
    assert "attachments" in first  # recommendation produced → card

    # Same role/goal again → recommendation is unchanged → no duplicate card, still text.
    second = await agent_host._agent_outbound(activity, "conv-agent-dup")
    assert second["text"].strip()
    assert "attachments" not in second


async def test_proactive_cold_start_from_body_reference(agent_host):
    """Agent opens a chat the user never messaged, using a body-supplied reference."""
    received: list[dict] = []

    async def collect(req: web.Request) -> web.Response:
        received.append(await req.json())
        return web.json_response({"id": f"srv-{len(received)}"})

    connector = web.Application()
    connector.router.add_post("/v3/conversations/{cid}/activities", collect)
    connector_server = TestServer(connector)
    await connector_server.start_server()
    service_url = str(connector_server.make_url("")).rstrip("/")

    client = TestClient(TestServer(agent_host.create_app()))
    await client.start_server()
    try:
        # No prior inbound activity for this conversation — pure cold start.
        resp = await client.post(
            "/api/proactive",
            json={
                "serviceUrl": service_url,
                "conversationId": "cold-conv",
                "prompt": "I'm a Developer and I want to Build an agent",
            },
        )
        assert resp.status == 200
        assert (await resp.json())["delivered"] is True
        assert len(received) == 1
        sent = received[0]
        assert sent["conversation"]["id"] == "cold-conv"
        # Agent authored the opener and pushed the recommendation card.
        assert sent["text"].strip()
        assert sent["attachments"][0]["content"]["type"] == "AdaptiveCard"
    finally:
        await client.close()
        await connector_server.close()
