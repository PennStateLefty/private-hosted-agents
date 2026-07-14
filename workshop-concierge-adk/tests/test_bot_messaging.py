"""G3 — Teams Bot Framework messaging adapter tests (offline).

Proves the deterministic translation the deployed Azure Bot messaging endpoint
runs: inbound Teams Activity -> teams_dispatch -> outbound Activity, with the
correlation id threaded onto every outbound Activity's channelData across the full
intake -> recommend -> accept round trip, using a single conversation-scoped session.
"""
from __future__ import annotations

from bot.messaging import (
    ADAPTIVE_CARD_CONTENT_TYPE,
    InMemorySessionStore,
    handle_activity,
)
from workshop_concierge import teams_dispatch


def _conv(activity_extra: dict) -> dict:
    base = {"conversation": {"id": "19:meeting_abc@thread.v2"}}
    base.update(activity_extra)
    return base


def _card_of(activity: dict) -> dict:
    assert activity["type"] == "message"
    att = activity["attachments"][0]
    assert att["contentType"] == ADAPTIVE_CARD_CONTENT_TYPE
    return att["content"]


def test_conversation_update_returns_intake_card():
    out = handle_activity(_conv({"type": "conversationUpdate"}))
    card = _card_of(out)
    assert card["type"] == "AdaptiveCard"
    corr = out["channelData"]["correlationId"]
    assert corr
    # correlation id is threaded onto the card's submit actions
    assert corr in teams_dispatch.submit_correlation_ids(card)


def test_message_without_value_starts_new_session():
    out = handle_activity(_conv({"type": "message", "text": "hi"}))
    assert out["attachments"][0]["content"]["type"] == "AdaptiveCard"


def test_missing_conversation_id_raises():
    import pytest

    with pytest.raises(ValueError):
        handle_activity({"type": "message", "value": {"action": "accept"}})


def test_full_round_trip_preserves_one_correlation_id():
    store = InMemorySessionStore()
    conv_id = "19:full_trip@thread.v2"

    # 1) open -> intake card
    open_out = handle_activity(
        {"type": "conversationUpdate", "conversation": {"id": conv_id}}, store
    )
    corr = open_out["channelData"]["correlationId"]
    intake = _card_of(open_out)
    assert corr in teams_dispatch.submit_correlation_ids(intake)

    # 2) submit intake -> recommendation card (same correlation, same session)
    rec_out = handle_activity(
        {
            "type": "message",
            "conversation": {"id": conv_id},
            "value": {
                "action": "submit_intake",
                "role": "developer",
                "goal": "build",
                "correlation_id": corr,
            },
        },
        store,
    )
    rec = _card_of(rec_out)
    assert rec_out["channelData"]["correlationId"] == corr
    assert corr in teams_dispatch.submit_correlation_ids(rec)

    # 3) accept -> final message, no external commitment, correlation intact
    accept_out = handle_activity(
        {
            "type": "message",
            "conversation": {"id": conv_id},
            "value": {"action": "accept", "correlation_id": corr},
        },
        store,
    )
    assert accept_out["type"] == "message"
    assert accept_out["channelData"]["correlationId"] == corr
    assert "no external system has been changed" in accept_out["text"].lower()
    assert accept_out["channelData"]["nextAction"].startswith("enroll_intent:")


def test_sessions_are_isolated_per_conversation():
    store = InMemorySessionStore()
    a = handle_activity(
        {"type": "conversationUpdate", "conversation": {"id": "conv-A"}}, store
    )
    b = handle_activity(
        {"type": "conversationUpdate", "conversation": {"id": "conv-B"}}, store
    )
    assert (
        a["channelData"]["correlationId"] != b["channelData"]["correlationId"]
    )
