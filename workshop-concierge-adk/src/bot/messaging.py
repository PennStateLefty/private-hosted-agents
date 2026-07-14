"""Bot Framework messaging adapter for Microsoft Teams.

This is the thin, deterministic translation layer a hosted Azure Bot messaging
endpoint runs: it converts an inbound Bot Framework ``Activity`` (a Teams
``Action.Submit`` arrives as an Activity whose ``value`` is the card ``data``, and a
conversation open arrives as a ``conversationUpdate``) into a
:mod:`workshop_concierge.teams_dispatch` call, then wraps the resulting Adaptive
Card / message back into an outbound Activity with the correlation id echoed in
``channelData`` so end-to-end tracing survives the Teams round trip.

Kept free of the ``botbuilder`` SDK / network types so the full
Teams-activity -> dispatch -> Teams-activity contract is unit-testable offline and
identical to what the deployed bot executes. Live delivery (Azure Bot + Teams
channel + public TLS ingress) is gated on the landing zone exposing a public
messaging endpoint — see ``evidence/G3-teams-publish.md``.
"""
from __future__ import annotations

from typing import Any, Protocol

from workshop_concierge import teams_dispatch
from workshop_concierge.session import ConciergeSession

ADAPTIVE_CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"


class SessionStore(Protocol):
    """Per-conversation session persistence. The deployed bot backs this with a
    durable store (e.g. Cosmos/Table); tests use an in-memory dict."""

    def get(self, conversation_id: str) -> ConciergeSession | None: ...

    def put(self, conversation_id: str, session: ConciergeSession) -> None: ...


class InMemorySessionStore:
    """Dict-backed :class:`SessionStore` (default; also used in tests)."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConciergeSession] = {}

    def get(self, conversation_id: str) -> ConciergeSession | None:
        return self._sessions.get(conversation_id)

    def put(self, conversation_id: str, session: ConciergeSession) -> None:
        self._sessions[conversation_id] = session


def _conversation_id(activity: dict) -> str:
    conv = activity.get("conversation") or {}
    cid = conv.get("id")
    if not cid:
        raise ValueError("Activity is missing conversation.id")
    return cid


def _card_attachment(card: dict) -> dict:
    return {"contentType": ADAPTIVE_CARD_CONTENT_TYPE, "content": card}


def _outbound(result: teams_dispatch.DispatchResult) -> dict:
    """Wrap a DispatchResult in a Bot Framework outbound message Activity.

    - "card"    -> message Activity with a single Adaptive Card attachment
    - "message" -> plain text message Activity
    - "error"   -> plain text message Activity (surfaced to the user)

    The correlation id is echoed in ``channelData.correlationId`` on every
    outbound Activity for end-to-end tracing.
    """
    activity: dict[str, Any] = {
        "type": "message",
        "channelData": {"correlationId": result.correlation_id},
    }
    if result.kind == "card":
        activity["attachments"] = [_card_attachment(result.payload)]
    else:
        activity["text"] = (result.payload or {}).get("text", "")
        if result.kind == "message" and (result.payload or {}).get("next_action"):
            activity["channelData"]["nextAction"] = result.payload["next_action"]
    return activity


def handle_activity(activity: dict, store: SessionStore | None = None) -> dict:
    """Translate one inbound Teams Activity into an outbound Activity.

    Supported inbound types:
      - ``conversationUpdate`` (or ``message`` with no ``value``): start a new
        conversation -> intake card.
      - ``message`` with a ``value`` (an ``Action.Submit`` payload): advance the
        session via the dispatcher.
    """
    store = store or InMemorySessionStore()
    conversation_id = _conversation_id(activity)
    a_type = activity.get("type", "message")
    value = activity.get("value")

    # Conversation start / greeting -> intake card (new session).
    if a_type == "conversationUpdate" or value is None:
        result = teams_dispatch.start()
        session = ConciergeSession(correlation_id=result.correlation_id)
        store.put(conversation_id, session)
        return _outbound(result)

    # Action.Submit -> advance the existing (or freshly created) session.
    session = store.get(conversation_id) or ConciergeSession()
    result = teams_dispatch.handle_submit(dict(value), session)
    store.put(conversation_id, session)
    return _outbound(result)
