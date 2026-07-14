"""Local Teams App Test Tool host — activity-adaptation tests (offline).

Exercises ``tools/teams-testtool/host.py`` end to end against a *fake* Bot Framework
connector (an in-process aiohttp server that records what the host posts back), proving:

* a conversation-open ``conversationUpdate`` proactively yields the intake card,
* an ``Action.Submit`` (``submit_intake``) advances to the recommendation card with the
  correlation id preserved across turns (shared process store),
* the ``/api/proactive`` endpoint delivers a real, untriggered message, and
* the host does not reply to the bot's own membersAdded join.

These are pure/offline: no Azure, no Teams, no auth. Skipped cleanly if aiohttp (the
test-only ``testtool`` extra) is not installed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("aiohttp")

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from workshop_concierge import teams_dispatch  # noqa: E402

# Load host.py from tools/teams-testtool/ (outside the src/ path pytest configures).
_HOST_PATH = (
    Path(__file__).resolve().parents[1] / "tools" / "teams-testtool" / "host.py"
)
_spec = importlib.util.spec_from_file_location("teams_testtool_host", _HOST_PATH)
host = importlib.util.module_from_spec(_spec)
sys.modules["teams_testtool_host"] = host
assert _spec and _spec.loader
_spec.loader.exec_module(host)


ADAPTIVE_CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"


@pytest.fixture(autouse=True)
def _reset_host_state():
    """Isolate the host's process-global session store / references per test."""
    host._STORE = host.InMemorySessionStore()
    host._REFERENCES.clear()
    yield
    host._REFERENCES.clear()


class _FakeConnector:
    """Records Activities the host POSTs to /v3/conversations/{id}/activities."""

    def __init__(self) -> None:
        self.received: list[dict] = []
        self.app = web.Application()
        self.app.router.add_post(
            "/v3/conversations/{cid}/activities", self._collect
        )

    async def _collect(self, request: web.Request) -> web.Response:
        self.received.append(await request.json())
        return web.json_response({"id": "srv-" + str(len(self.received))})


async def _make_clients():
    connector = _FakeConnector()
    connector_server = TestServer(connector.app)
    await connector_server.start_server()
    service_url = str(connector_server.make_url("")).rstrip("/")

    host_client = TestClient(TestServer(host.create_app()))
    await host_client.start_server()
    return connector, connector_server, host_client, service_url


def _card(activity: dict) -> dict:
    assert activity["type"] == "message"
    att = activity["attachments"][0]
    assert att["contentType"] == ADAPTIVE_CARD_CONTENT_TYPE
    return att["content"]


def _conv_update(service_url: str, conv_id: str) -> dict:
    return {
        "type": "conversationUpdate",
        "id": "act-open",
        "serviceUrl": service_url,
        "channelId": "emulator",
        "conversation": {"id": conv_id},
        "recipient": {"id": "bot-1", "name": "Workshop Concierge"},
        "from": {"id": "user-1", "name": "Tester"},
        "membersAdded": [{"id": "user-1"}],
    }


async def test_conversation_open_proactively_sends_intake_card():
    connector, connector_server, client, service_url = await _make_clients()
    try:
        resp = await client.post(
            host.MESSAGES_PATH, json=_conv_update(service_url, "conv-A")
        )
        assert resp.status == 200
        assert len(connector.received) == 1
        card = _card(connector.received[0])
        assert card["type"] == "AdaptiveCard"
        # correlation id is threaded onto the card's submit actions
        assert teams_dispatch.submit_correlation_ids(card)
        # addressed back to the user, from the bot, in the same conversation
        sent = connector.received[0]
        assert sent["from"]["id"] == "bot-1"
        assert sent["recipient"]["id"] == "user-1"
        assert sent["conversation"]["id"] == "conv-A"
    finally:
        await client.close()
        await connector_server.close()


async def test_submit_intake_advances_to_recommendation_same_correlation():
    connector, connector_server, client, service_url = await _make_clients()
    try:
        # 1) open → intake card
        await client.post(host.MESSAGES_PATH, json=_conv_update(service_url, "conv-B"))
        intake = _card(connector.received[0])
        corr = teams_dispatch.submit_correlation_ids(intake)[0]

        # 2) submit intake → recommendation card, same session + correlation id
        submit = {
            "type": "message",
            "id": "act-submit",
            "serviceUrl": service_url,
            "channelId": "emulator",
            "conversation": {"id": "conv-B"},
            "recipient": {"id": "bot-1"},
            "from": {"id": "user-1"},
            "value": {
                "action": "submit_intake",
                "role": "Developer",
                "goal": "Build an agent",
                "correlation_id": corr,
            },
        }
        resp = await client.post(host.MESSAGES_PATH, json=submit)
        assert resp.status == 200
        assert len(connector.received) == 2
        rec = _card(connector.received[1])
        assert rec["type"] == "AdaptiveCard"
        assert connector.received[1]["channelData"]["correlationId"] == corr
        assert corr in teams_dispatch.submit_correlation_ids(rec)
    finally:
        await client.close()
        await connector_server.close()


async def test_bot_only_membersadded_is_not_answered():
    connector, connector_server, client, service_url = await _make_clients()
    try:
        activity = _conv_update(service_url, "conv-C")
        activity["membersAdded"] = [{"id": "bot-1"}]  # only the bot joined
        resp = await client.post(host.MESSAGES_PATH, json=activity)
        assert resp.status == 200
        assert connector.received == []  # no proactive reply to our own join
    finally:
        await client.close()
        await connector_server.close()


async def test_proactive_endpoint_delivers_untriggered_message():
    connector, connector_server, client, service_url = await _make_clients()
    try:
        # Prime a known conversation reference via one inbound activity.
        await client.post(host.MESSAGES_PATH, json=_conv_update(service_url, "conv-D"))
        assert len(connector.received) == 1

        resp = await client.post(
            "/api/proactive", json={"conversationId": "conv-D", "text": "ping"}
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["delivered"] is True
        assert len(connector.received) == 2
        assert connector.received[1]["text"] == "ping"
        assert connector.received[1]["conversation"]["id"] == "conv-D"
    finally:
        await client.close()
        await connector_server.close()


async def test_proactive_without_known_conversation_is_409():
    client = TestClient(TestServer(host.create_app()))
    await client.start_server()
    try:
        resp = await client.post("/api/proactive", json={"text": "nope"})
        assert resp.status == 409
    finally:
        await client.close()


async def test_health_endpoint():
    client = TestClient(TestServer(host.create_app()))
    await client.start_server()
    try:
        resp = await client.get("/health")
        assert resp.status == 200
        assert (await resp.json())["status"] == "ok"
    finally:
        await client.close()

# --- Agent mode (offline paths that don't need google-adk / the model) -------
# _agent_outbound imports agent_bridge lazily, only when it actually runs a turn, so the
# greeting and empty-message branches are exercisable on Python 3.14 without the ADK stack.

async def test_agent_mode_conversationupdate_greets_without_adk():
    activity = {"type": "conversationUpdate", "conversation": {"id": "c1"}}
    out = await host._agent_outbound(activity, "c1")
    assert out is not None
    assert out["type"] == "message"
    assert out["text"] == host.AGENT_GREETING
    assert "attachments" not in out  # agent mode replies with text, not a card


async def test_agent_mode_empty_message_returns_none_without_adk():
    activity = {"type": "message", "text": "   ", "conversation": {"id": "c1"}}
    out = await host._agent_outbound(activity, "c1")
    assert out is None
