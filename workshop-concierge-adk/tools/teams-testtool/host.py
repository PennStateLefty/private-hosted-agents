"""LOCAL, TEST-ONLY Bot Framework messaging host for the Microsoft Teams App Test Tool.

This is a thin, offline rig that lets a developer exercise the Teams integration in
the Teams App Test Tool ("Teams playground") with **no** M365 tenant/license, **no**
Azure Bot registration and **no** tunnel. It is NEVER deployed — production Teams
delivery is served by the Foundry Hosted Agent's native ``activity`` protocol (see
``KNOWN-ISSUES.md`` #1 / ``architecture/decisions/ADR-001-teams-public-ingress.md``).
Do not wire this into ``azure.yaml`` / ``infra`` / azd.

It reuses the existing, deterministic translation layer unchanged:
``bot.messaging.handle_activity(activity, store)`` → outbound Activity dict, which in
turn calls ``workshop_concierge.teams_dispatch`` and ``workshop_concierge.cards``. No
card or dispatch logic is reimplemented here — this file only speaks the local
connector protocol (receive Activity → reply Activity) and adds proactive initiation.

Protocol (matches how the Test Tool / Bot Framework connector work):
  * The Test Tool POSTs inbound Activities to ``POST /api/messages`` (default :3978)
    and includes a local ``serviceUrl`` connector.
  * The bot replies by POSTing the outbound Activity to
    ``{serviceUrl}/v3/conversations/{conversationId}/activities``.
  * On conversation open the Test Tool sends a ``conversationUpdate`` with
    ``membersAdded`` → the bot **proactively initiates** with the intake card.

Why raw aiohttp (not botbuilder-core): this machine runs Python 3.14, on which the
pinned ``botbuilder-core`` / ``litellm`` stack does not install. The Test Tool requires
no bot auth, so a minimal connector client is sufficient and dependency-light.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

from aiohttp import ClientSession, web

# ``handle_activity`` and the in-memory store come straight from the shipped code.
from bot.messaging import InMemorySessionStore, handle_activity

LOG = logging.getLogger("teams-testtool-host")

MESSAGES_PATH = "/api/messages"
DEFAULT_PORT = 3978

# ---------------------------------------------------------------------------
# Host mode
# ---------------------------------------------------------------------------
# ``dispatch`` (default): reuse the deterministic ``bot.messaging.handle_activity``
#   card state machine — no LLM, importable on Python 3.14.
# ``agent``: drive the REAL ADK ``LlmAgent`` against the Foundry model via
#   ``agent_bridge`` and emit OpenTelemetry spans (see ``run-bot-agent.sh``). Requires
#   the Python 3.13 ``.venv-agent`` + VPN + model RBAC. Heavy imports stay lazy so this
#   file still imports in dispatch mode on 3.14.
_AGENT_MODE = os.environ.get("WC_HOST_MODE", "dispatch").strip().lower() == "agent"

# Text the agent proactively opens with on conversation open (agent *initiates*). Kept
# deterministic so opening a chat costs no model call; the first user message is what
# exercises the real agent + telemetry.
AGENT_GREETING = (
    "👋 Hi, I'm the Workshop Concierge. Tell me about your goals or background and I'll "
    "recommend a workshop track for you."
)

# Correlation id per conversation, so tool spans + the turn span share an id in agent mode.
_CORR: dict[str, str] = {}

# Typed application key for the shared aiohttp client (aiohttp best practice).
CLIENT_KEY: "web.AppKey[ClientSession]" = web.AppKey("client", ClientSession)

# One shared, process-wide session store so a conversation's state (intake →
# recommendation → accept) survives across turns exactly like the deployed bot's
# durable store would.
_STORE = InMemorySessionStore()

# Last inbound conversation reference per conversation id, so a *real* proactive
# message can be sent later without an inbound trigger (see ``/api/proactive``).
_REFERENCES: dict[str, dict[str, Any]] = {}


def _bot_id(activity: dict) -> Optional[str]:
    return (activity.get("recipient") or {}).get("id")


def _conversation_reference(inbound: dict) -> dict[str, Any]:
    """Capture the fields needed to address a reply/proactive Activity back to the
    Test Tool connector for this conversation."""
    return {
        "serviceUrl": inbound.get("serviceUrl", ""),
        "channelId": inbound.get("channelId", "emulator"),
        "conversation": inbound.get("conversation") or {},
        # For a reply, ``from`` is the bot and ``recipient`` is the user, so we swap
        # the inbound endpoints.
        "bot": inbound.get("recipient") or {},
        "user": inbound.get("from") or {},
        "replyToId": inbound.get("id"),
    }


def _envelope(outbound: dict, ref: dict[str, Any]) -> dict[str, Any]:
    """Turn the minimal Activity from ``handle_activity`` into a fully-addressed
    outbound Activity the connector will render (from/recipient/conversation/id)."""
    activity = dict(outbound)
    activity.setdefault("type", "message")
    activity["id"] = uuid.uuid4().hex
    activity["from"] = ref.get("bot") or {"id": "workshop-concierge", "name": "Workshop Concierge"}
    activity["recipient"] = ref.get("user") or {}
    activity["conversation"] = ref.get("conversation") or {}
    if ref.get("channelId"):
        activity["channelId"] = ref["channelId"]
    if ref.get("serviceUrl"):
        activity["serviceUrl"] = ref["serviceUrl"]
    if ref.get("replyToId"):
        activity["replyToId"] = ref["replyToId"]
    return activity


async def _send_to_connector(session: ClientSession, ref: dict[str, Any], activity: dict) -> None:
    """POST an outbound Activity to the local Test Tool connector."""
    service_url = (ref.get("serviceUrl") or "").rstrip("/")
    conversation_id = (ref.get("conversation") or {}).get("id")
    if not service_url or not conversation_id:
        LOG.warning("no serviceUrl/conversation.id — cannot deliver reply; ref=%s", ref)
        return
    url = f"{service_url}/v3/conversations/{conversation_id}/activities"
    async with session.post(url, json=activity) as resp:
        body = await resp.text()
        LOG.info("→ connector %s [%s] %s", url, resp.status, body[:200])


def _should_initiate(activity: dict) -> bool:
    """A conversationUpdate should proactively initiate only when a non-bot member is
    added (the user opening the chat), so the bot doesn't reply to its own join."""
    if activity.get("type") != "conversationUpdate":
        return True  # message activities are always handled
    bot_id = _bot_id(activity)
    added = activity.get("membersAdded") or []
    return any((m or {}).get("id") != bot_id for m in added)


async def handle_messages(request: web.Request) -> web.Response:
    """``POST /api/messages`` — inbound Activity → reply Activity via the connector."""
    try:
        activity = await request.json()
    except Exception:  # noqa: BLE001 - malformed body from the tool
        return web.json_response({"error": "invalid JSON activity"}, status=400)

    if not isinstance(activity, dict):
        return web.json_response({"error": "activity must be an object"}, status=400)

    # Remember how to reach this conversation for later proactive sends.
    ref = _conversation_reference(activity)
    conv_id = (ref.get("conversation") or {}).get("id")
    if conv_id:
        _REFERENCES[conv_id] = ref

    if not _should_initiate(activity):
        # e.g. the bot's own conversationUpdate join — acknowledge with no reply.
        return web.Response(status=200)

    if _AGENT_MODE:
        outbound = await _agent_outbound(activity, conv_id)
        if outbound is None:
            return web.Response(status=200)
        envelope = _envelope(outbound, ref)
        session: ClientSession = request.app[CLIENT_KEY]
        await _send_to_connector(session, ref, envelope)
        return web.Response(status=200)

    try:
        outbound = handle_activity(activity, _STORE)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)

    envelope = _envelope(outbound, ref)
    session: ClientSession = request.app[CLIENT_KEY]
    await _send_to_connector(session, ref, envelope)
    return web.Response(status=200)


async def _agent_outbound(activity: dict, conv_id: Optional[str]) -> Optional[dict]:
    """Agent-mode outbound: drive the REAL ADK agent (or greet on conversation open).

    Returns a minimal outbound Activity dict, or ``None`` when there's nothing to say
    (e.g. an empty message). Heavy deps are imported lazily here so dispatch mode never
    pays for them.
    """
    if activity.get("type") == "conversationUpdate":
        return {"type": "message", "text": AGENT_GREETING}

    text = activity.get("text") or ""
    if not text.strip():
        value = activity.get("value")
        text = str(value) if value else ""
    if not text.strip():
        return None

    # Import the heavy agent stack only when we actually run a turn, so the greeting /
    # empty-message paths (and their unit tests) don't need google-adk / py3.13.
    import agent_bridge  # noqa: PLC0415 — lazy: deps live under .venv-agent (py3.13)

    key = conv_id or "default"
    corr = _CORR.setdefault(key, agent_bridge.new_correlation_id())
    try:
        reply = await agent_bridge.run_agent_turn(conv_id, text, corr)
    except Exception as exc:  # noqa: BLE001 - surface agent/model failures to the tool UI
        LOG.exception("agent turn failed")
        reply = f"(agent error: {exc})"
    return {
        "type": "message",
        "text": reply or "(no response)",
        "channelData": {"correlationId": corr},
    }


async def handle_proactive(request: web.Request) -> web.Response:
    """``POST /api/proactive`` — prove a *real* proactive message works.

    Sends the intake card (or a supplied text) to a known conversation without any
    inbound trigger, using the stored conversation reference. Body (all optional):
    ``{"conversationId": "...", "text": "..."}``. With no conversationId the most
    recent conversation is used.
    """
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}

    conv_id = (payload or {}).get("conversationId")
    ref = _REFERENCES.get(conv_id) if conv_id else (
        next(reversed(_REFERENCES.values())) if _REFERENCES else None
    )
    if not ref:
        return web.json_response(
            {"error": "no known conversation yet — open the chat in the Test Tool first"},
            status=409,
        )

    text = (payload or {}).get("text")
    if text:
        outbound = {"type": "message", "text": text}
    elif _AGENT_MODE:
        # Agent mode has no card state machine — proactively initiate with the greeting.
        outbound = {"type": "message", "text": AGENT_GREETING}
    else:
        # Reuse the exact intake card the deployed bot would proactively send by
        # replaying a synthetic conversationUpdate through handle_activity.
        synthetic = {
            "type": "conversationUpdate",
            "conversation": ref.get("conversation") or {},
        }
        outbound = handle_activity(synthetic, _STORE)

    envelope = _envelope(outbound, {**ref, "replyToId": None})
    session: ClientSession = request.app[CLIENT_KEY]
    await _send_to_connector(session, ref, envelope)
    return web.json_response({"delivered": True, "conversationId": (ref.get("conversation") or {}).get("id")})


async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "conversations": len(_REFERENCES)})


async def _on_startup(app: web.Application) -> None:
    app[CLIENT_KEY] = ClientSession()


async def _on_cleanup(app: web.Application) -> None:
    client: ClientSession = app.get(CLIENT_KEY)
    if client is not None:
        await client.close()


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post(MESSAGES_PATH, handle_messages)
    app.router.add_post("/api/proactive", handle_proactive)
    app.router.add_get("/health", handle_health)
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    return app


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if _AGENT_MODE and os.environ.get("WC_TELEMETRY", "console").strip().lower() != "off":
        # Install the console span exporter BEFORE the first turn so agent + tool spans
        # print to this terminal. Lazy import keeps dispatch mode dependency-light.
        import telemetry

        telemetry.setup_console_tracing()
        LOG.info("console OpenTelemetry enabled (spans print below during each turn)")
    port = int(os.environ.get("BOT_PORT") or os.environ.get("PORT") or DEFAULT_PORT)
    mode = "AGENT (real ADK + Foundry)" if _AGENT_MODE else "dispatch (deterministic cards)"
    LOG.info(
        "Workshop Concierge Teams Test Tool host on :%d%s — mode=%s (LOCAL TEST ONLY)",
        port, MESSAGES_PATH, mode,
    )
    web.run_app(create_app(), host="localhost", port=port)


if __name__ == "__main__":
    main()
