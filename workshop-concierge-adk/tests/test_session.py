"""Unit tests for session-state stage transitions and the bounded loop."""
import pytest

from workshop_concierge.session import (
    ConciergeSession,
    Stage,
    TransitionError,
    MAX_ALTERNATIVES,
)


def test_happy_path_intake_recommend_accept():
    s = ConciergeSession(correlation_id="corr-1", conversation_id="conv-1")
    assert s.stage is Stage.INTAKE
    rec = s.submit_intake("Developer", "Build an agent")
    assert s.stage is Stage.RECOMMENDED
    assert rec["track_id"] == "build"
    final = s.accept()
    assert final == "build"
    assert s.stage is Stage.CONFIRMED
    # Next action is recorded, not executed against any external system.
    assert s.next_action == "enroll_intent:build"


def test_show_alternative_is_bounded_to_one():
    s = ConciergeSession()
    s.submit_intake("Developer", "Build an agent")
    first = s.recommendation["track_id"]
    alt = s.show_alternative()
    assert s.alternative_count == MAX_ALTERNATIVES
    assert alt["track_id"] != first
    # A second alternative must be refused.
    with pytest.raises(TransitionError):
        s.show_alternative()


def test_accept_after_alternative():
    s = ConciergeSession()
    s.submit_intake("Architect", "Integrate an agent")
    alt = s.show_alternative()
    final = s.accept()
    assert final == alt["track_id"]
    assert s.stage is Stage.CONFIRMED


def test_cannot_accept_before_recommendation():
    s = ConciergeSession()
    with pytest.raises(TransitionError):
        s.accept()


def test_cannot_alternative_before_recommendation():
    s = ConciergeSession()
    with pytest.raises(TransitionError):
        s.show_alternative()


def test_start_over_resets_state():
    s = ConciergeSession()
    s.submit_intake("Developer", "Build an agent")
    s.accept()
    s.start_over()
    assert s.stage is Stage.INTAKE
    assert s.role is None and s.goal is None
    assert s.recommendation is None
    assert s.alternative_count == 0
    # After start over, a fresh intake works again.
    rec = s.submit_intake("Business leader", "Govern and operate agents")
    assert rec["track_id"] == "govern"


def test_intake_after_confirm_requires_start_over():
    s = ConciergeSession()
    s.submit_intake("Developer", "Build an agent")
    s.accept()
    with pytest.raises(TransitionError):
        s.submit_intake("Architect", "Integrate an agent")


def test_state_roundtrip():
    s = ConciergeSession(correlation_id="c-9")
    s.submit_intake("Architect", "Govern and operate agents")
    state = s.to_state()
    restored = ConciergeSession.from_state(state)
    assert restored.stage is Stage.RECOMMENDED
    assert restored.role == "architect"
    assert restored.recommendation["track_id"] == "govern"
    assert restored.correlation_id == "c-9"
