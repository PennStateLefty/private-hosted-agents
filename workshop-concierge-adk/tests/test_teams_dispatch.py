"""G4 — Adaptive Card + callback correlation tests.

Proves the full card -> Action.Submit -> next-card chain preserves a single
correlation id end-to-end, that the bounded single-alternative rule holds across
the callback boundary, and that acceptance makes no external commitment.
"""
from __future__ import annotations

import pytest

from workshop_concierge import cards, teams_dispatch
from workshop_concierge.session import ConciergeSession


CORR = "wc-test-correlation-001"


def _submit_ids(result_card):
    return teams_dispatch.submit_correlation_ids(result_card)


def test_intake_card_carries_correlation():
    r = teams_dispatch.start(CORR)
    assert r.kind == "card"
    assert r.correlation_id == CORR
    assert _submit_ids(r.payload) == [CORR]


def test_full_chain_preserves_single_correlation_id():
    session = ConciergeSession(correlation_id=CORR)

    # Intake submit -> recommendation card
    r1 = teams_dispatch.handle_submit(
        {"action": "submit_intake", "role": "Developer",
         "goal": "Build an agent", "correlation_id": CORR},
        session,
    )
    assert r1.kind == "card"
    assert r1.correlation_id == CORR
    # Every action on the recommendation card carries the same correlation id.
    assert set(_submit_ids(r1.payload)) == {CORR}
    # The recommendation is the deterministic Build track.
    assert "Build" in r1.payload["body"][1]["text"]

    # Show alternative -> bounded card (no further alternative offered)
    r2 = teams_dispatch.handle_submit(
        {"action": "show_alternative", "correlation_id": CORR}, session
    )
    assert r2.correlation_id == CORR
    titles = [a["title"] for a in r2.payload["actions"]]
    assert "Show alternative" not in titles  # bounded to one
    assert set(_submit_ids(r2.payload)) == {CORR}

    # A second alternative must be refused across the callback boundary.
    r3 = teams_dispatch.handle_submit(
        {"action": "show_alternative", "correlation_id": CORR}, session
    )
    assert r3.kind == "error"
    assert r3.correlation_id == CORR

    # Accept -> message, correlation preserved, no external commitment claimed.
    r4 = teams_dispatch.handle_submit({"action": "accept", "correlation_id": CORR}, session)
    assert r4.kind == "message"
    assert r4.correlation_id == CORR
    assert "no external system" in r4.payload["text"].lower()
    assert r4.payload["next_action"].startswith("enroll_intent:")


def test_correlation_survives_when_only_session_has_it():
    # A submit that omits correlation_id inherits it from the session.
    session = ConciergeSession(correlation_id=CORR)
    r = teams_dispatch.handle_submit(
        {"action": "submit_intake", "role": "Architect", "goal": "Integrate an agent"},
        session,
    )
    assert r.correlation_id == CORR
    assert set(_submit_ids(r.payload)) == {CORR}


def test_correlation_minted_when_absent_everywhere():
    session = ConciergeSession()
    r = teams_dispatch.handle_submit(
        {"action": "submit_intake", "role": "Business leader",
         "goal": "Govern and operate agents"},
        session,
    )
    assert r.correlation_id.startswith("wc-")
    # Minted id is written back to the session and threaded onto the card.
    assert session.correlation_id == r.correlation_id
    assert set(_submit_ids(r.payload)) == {r.correlation_id}


def test_start_over_returns_intake_with_same_correlation():
    session = ConciergeSession(correlation_id=CORR)
    teams_dispatch.handle_submit(
        {"action": "submit_intake", "role": "Developer",
         "goal": "Build an agent", "correlation_id": CORR},
        session,
    )
    r = teams_dispatch.handle_submit({"action": "start_over", "correlation_id": CORR}, session)
    assert r.kind == "card"
    assert r.correlation_id == CORR
    assert _submit_ids(r.payload) == [CORR]


def test_unknown_action_is_correlated_error():
    session = ConciergeSession(correlation_id=CORR)
    r = teams_dispatch.handle_submit({"action": "bogus", "correlation_id": CORR}, session)
    assert r.kind == "error"
    assert r.correlation_id == CORR
