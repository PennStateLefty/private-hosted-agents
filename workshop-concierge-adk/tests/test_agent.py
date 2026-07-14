"""Offline tests: agent wiring, the tool's state effects, and card structure.

These do not call the model or the network — they prove the plumbing that the
Responses adapter and the hosted deployment rely on.
"""
import types

import pytest

from workshop_concierge import agent as agent_mod
from workshop_concierge import cards


class _StubToolContext:
    """Minimal stand-in exposing the mutable .state dict the tool uses."""

    def __init__(self, state=None):
        self.state = state if state is not None else {}


def test_agent_builds_offline_with_injected_model():
    a = agent_mod.create_agent(model="azure/chat")  # no network at construction
    assert a.name == "workshop_concierge"
    tool_names = {getattr(t, "name", None) for t in a.tools}
    assert "recommend_track" in tool_names
    assert a.before_agent_callback is not None
    assert a.after_tool_callback is not None


def test_tool_updates_session_state():
    ctx = _StubToolContext()
    out = agent_mod.recommend_track("Developer", "Build an agent", tool_context=ctx)
    assert out["track_id"] == "build"
    assert ctx.state["role"] == "developer"
    assert ctx.state["goal"] == "build_agent"
    assert ctx.state["stage"] == "recommended"
    assert ctx.state["recommendation"]["track_id"] == "build"
    assert ctx.state["last_tool"] == "recommend_track"


def test_tool_alternative_increments_counter():
    ctx = _StubToolContext()
    agent_mod.recommend_track("Developer", "Build an agent", tool_context=ctx)
    assert ctx.state["alternative_count"] == 0
    out = agent_mod.recommend_track(
        "Developer", "Build an agent", excluded_track="build", tool_context=ctx
    )
    assert out["track_id"] != "build"
    assert ctx.state["alternative_count"] == 1


def test_tool_returns_error_shape_on_invalid_input():
    ctx = _StubToolContext()
    out = agent_mod.recommend_track("chef", "cook", tool_context=ctx)
    assert "error" in out
    assert "track_id" not in out


def test_derive_openai_endpoint(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://aif-x.services.ai.azure.com/api/projects/p1",
    )
    assert agent_mod._derive_openai_endpoint() == "https://aif-x.services.ai.azure.com"
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://explicit.openai.azure.com/")
    assert agent_mod._derive_openai_endpoint() == "https://explicit.openai.azure.com"


def test_intake_card_structure():
    card = cards.intake_card("corr-123")
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == cards.ADAPTIVE_CARD_VERSION
    ids = {el["id"] for el in card["body"] if "id" in el}
    assert {"role", "goal"} <= ids
    submit = card["actions"][0]
    assert submit["data"]["action"] == "submit_intake"
    assert submit["data"]["correlation_id"] == "corr-123"


def test_recommendation_card_actions():
    from workshop_concierge import recommend

    rec = recommend.recommend_track("Architect", "Integrate an agent")
    card = cards.recommendation_card(rec, "corr-9")
    actions = {a["data"]["action"] for a in card["actions"]}
    assert actions == {"accept", "show_alternative", "start_over"}
    # Alternative can be suppressed after it's already been used once.
    card2 = cards.recommendation_card(rec, "corr-9", allow_alternative=False)
    actions2 = {a["data"]["action"] for a in card2["actions"]}
    assert "show_alternative" not in actions2


def test_card_catalog_alignment():
    cards.validate_catalog_alignment()
