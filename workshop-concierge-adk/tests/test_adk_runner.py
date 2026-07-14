"""Offline ADK-path test: real Runner + tool, scripted FakeLlm (no network).

Proves that a Responses-style turn drives the ADK agent, executes the
deterministic recommend_track tool, updates session state, and returns text —
i.e. the Responses->ADK->tool->output mapping the hosted deployment relies on.
"""
import pytest

from adapter.adk_runner import ConciergeRunner
from fakes import FakeLlm

pytestmark = pytest.mark.asyncio


async def test_turn_invokes_tool_and_returns_text():
    runner = ConciergeRunner(model=FakeLlm(model="fake"))
    reply = await runner.run_turn(
        "conv-1", "I'm a Developer and I want to Build an agent", correlation_id="corr-1"
    )
    assert "build" in reply.lower()

    # The tool ran and wrote the recommendation into session state.
    session = await runner.session_service.get_session(
        app_name=runner.app_name, user_id=runner.user_id, session_id="conv-1"
    )
    assert session.state.get("recommendation", {}).get("track_id") == "build"
    assert session.state.get("last_tool") == "recommend_track"
    assert session.state.get("correlation_id") == "corr-1"


async def test_conversation_continuity_same_session():
    runner = ConciergeRunner(model=FakeLlm(model="fake"))
    await runner.run_turn("conv-2", "I'm an Architect and I want to Integrate an agent")
    # Second turn reuses the same ADK session id.
    await runner.run_turn("conv-2", "show me the alternative")
    session = await runner.session_service.get_session(
        app_name=runner.app_name, user_id=runner.user_id, session_id="conv-2"
    )
    # Session persisted across turns (history has >1 model/user events).
    assert session is not None
    assert session.state.get("recommendation") is not None


async def test_empty_input_raises_explicit_error():
    runner = ConciergeRunner(model=FakeLlm(model="fake"))
    with pytest.raises(ValueError):
        await runner.run_turn("conv-3", "   ")


async def test_get_recommendation_surfaces_tool_result_from_state():
    runner = ConciergeRunner(model=FakeLlm(model="fake"))
    # No turn yet → nothing to surface.
    assert await runner.get_recommendation("conv-4") is None

    await runner.run_turn("conv-4", "I'm a Developer and I want to Build an agent")
    rec = await runner.get_recommendation("conv-4")
    assert rec is not None
    assert rec["recommendation"]["track_id"] == "build"
    # First recommendation → the single alternative is still offerable.
    assert rec["allow_alternative"] is True
    # Unknown conversation stays None.
    assert await runner.get_recommendation("no-such-conv") is None
