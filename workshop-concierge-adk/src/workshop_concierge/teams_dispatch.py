"""Adaptive Card callback dispatcher with end-to-end correlation.

A Teams / Bot Service messaging endpoint receives an ``Action.Submit`` as an
Activity whose ``value`` is the card's ``data`` payload. This module is the pure,
deterministic core that maps such a submit to a session transition and returns the
next Adaptive Card (or a final message), **preserving the correlation id** carried on
the inbound submit through the session and onto every outbound card action.

Keeping this handler free of Bot Framework / network types makes the full
card -> callback -> card correlation chain unit-testable offline and identical to
what the hosted bot executes. The live Teams delivery path (Bot Service + ingress)
is G3; this is the request/response correlation contract G4 requires.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from . import cards
from .session import ConciergeSession, TransitionError


@dataclass
class DispatchResult:
    kind: str  # "card" | "message" | "error"
    payload: Any
    correlation_id: str
    action: str


def _correlation_of(data: dict, session: ConciergeSession) -> str:
    """Resolve the correlation id: prefer the inbound submit, else the session,
    else mint a stable new one. The chosen id is written back to the session so
    every subsequent turn in the conversation shares it."""
    corr = (data or {}).get("correlation_id") or session.correlation_id
    if not corr:
        corr = f"wc-{uuid.uuid4().hex[:12]}"
    session.correlation_id = corr
    return corr


def start(correlation_id: Optional[str] = None) -> DispatchResult:
    """Emit the initial intake card for a new conversation."""
    session = ConciergeSession(correlation_id=correlation_id)
    corr = _correlation_of({}, session)
    return DispatchResult("card", cards.intake_card(corr), corr, "start")


def handle_submit(data: dict, session: ConciergeSession) -> DispatchResult:
    """Apply one Action.Submit to the session and return the next card/message.

    ``data`` is the Adaptive Card ``Action.Submit`` payload (``action`` +
    ``correlation_id`` + any inputs). The returned card always carries the same
    correlation id, so the round trip is correlatable end-to-end.
    """
    corr = _correlation_of(data, session)
    action = (data or {}).get("action", "")

    try:
        if action == "submit_intake":
            rec = session.submit_intake(data.get("role", ""), data.get("goal", ""))
            card = cards.recommendation_card(rec, corr, allow_alternative=True)
            return DispatchResult("card", card, corr, action)

        if action == "show_alternative":
            rec = session.show_alternative()
            # Bounded: after the single alternative, no further alternative offered.
            card = cards.recommendation_card(rec, corr, allow_alternative=False)
            return DispatchResult("card", card, corr, action)

        if action == "accept":
            track = session.accept()
            msg = {
                "type": "message",
                "text": (
                    f"You're set for the {track.capitalize()} track. "
                    "I've recorded your enrollment intent — no external system "
                    "has been changed."
                ),
                "correlation_id": corr,
                "next_action": session.next_action,
            }
            return DispatchResult("message", msg, corr, action)

        if action == "start_over":
            session.start_over()
            return DispatchResult("card", cards.intake_card(corr), corr, action)

    except TransitionError as exc:
        return DispatchResult(
            "error",
            {"type": "message", "text": str(exc), "correlation_id": corr},
            corr,
            action,
        )

    return DispatchResult(
        "error",
        {"type": "message", "text": f"Unknown action: {action!r}", "correlation_id": corr},
        corr,
        action,
    )


def submit_correlation_ids(card: dict) -> list[str]:
    """Return every correlation id embedded in a card's Action.Submit data
    (used by tests/telemetry to assert correlation is threaded onto outputs)."""
    ids = []
    for action in card.get("actions", []):
        cid = (action.get("data") or {}).get("correlation_id")
        if cid is not None:
            ids.append(cid)
    return ids
