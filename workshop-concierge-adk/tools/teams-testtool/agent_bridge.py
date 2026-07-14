"""Bridge from the LOCAL Test Tool host to the REAL ADK agent (test-only).

In *agent mode* the host stops using the deterministic ``teams_dispatch`` card state
machine and instead drives the actual Google ADK ``LlmAgent`` — the same agent that
runs in the Foundry Hosted Agent — via :class:`adapter.adk_runner.ConciergeRunner`.
Each turn is wrapped in a ``teams.turn`` span so, together with the console exporter in
:mod:`telemetry` and the tool spans ``agent.py`` emits, you can watch the model
orchestrate the response (tool call → recommended track → narrated reply).

Heavy imports (google-adk / litellm / azure-identity) are done lazily so the default
dispatch mode of the host stays importable on Python 3.14, where this stack won't
install. Agent mode must be run from the Python 3.13 ``.venv-agent`` (see
``run-bot-agent.sh``).
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Optional

_runner: Any = None


@dataclass
class AgentTurn:
    """Result of one real agent turn.

    ``text`` is the agent's narrated reply. ``recommendation`` is set **only when the
    ``recommend_track`` tool produced (or changed) a recommendation during this turn**,
    so the host can attach the shared recommendation Adaptive Card exactly once — the
    same card the deterministic dispatch flow sends — over the Activity Protocol.
    ``allow_alternative`` mirrors the bounded "show one alternative" rule.
    """

    text: str
    recommendation: Optional[dict] = None
    allow_alternative: bool = True


def _build_model() -> Any:
    """Resolve the model for the agent.

    - ``WC_MODEL=stub`` → an injected model name string; the agent object builds but is
      NOT executed against a network (used only for import/telemetry-wiring checks).
    - otherwise → ``None`` so ``create_agent`` builds the real Foundry model via
      ``DefaultAzureCredential`` (requires VPN + ``Cognitive Services OpenAI User``).
    """
    if os.environ.get("WC_MODEL") == "stub":
        return "azure/chat"
    return None


def get_runner() -> Any:
    """Lazily construct and cache the process-wide ADK runner."""
    global _runner
    if _runner is None:
        from adapter.adk_runner import ConciergeRunner

        _runner = ConciergeRunner(model=_build_model())
    return _runner


async def run_agent_turn(
    conversation_id: Optional[str], text: str, correlation_id: Optional[str]
) -> AgentTurn:
    """Run one real agent turn, wrapped in a ``teams.turn`` span.

    Returns an :class:`AgentTurn` carrying the agent's final assistant text and, when
    the ``recommend_track`` tool produced a *new* recommendation this turn, that
    recommendation so the host can push the recommendation Adaptive Card. The span
    carries the conversation id, correlation id, and input/output sizes so the console
    trace lines up with the tool spans ``agent.py`` records inside the same turn.
    """
    import telemetry

    tracer = telemetry.get_tracer("teams-testtool")
    with tracer.start_as_current_span("teams.turn") as span:
        span.set_attribute("teams.conversation_id", conversation_id or "")
        span.set_attribute("workshop.correlation_id", correlation_id or "")
        span.set_attribute("teams.input_chars", len(text or ""))
        runner = get_runner()
        # Snapshot the recommendation before/after so we only surface (and card) a
        # recommendation the model actually produced or changed on this turn — not one
        # left in session state from an earlier turn.
        before = await runner.get_recommendation(conversation_id)
        reply = await runner.run_turn(conversation_id, text, correlation_id)
        after = await runner.get_recommendation(conversation_id)
        span.set_attribute("teams.output_chars", len(reply or ""))

        turn = AgentTurn(text=reply)
        if after is not None and after != before:
            turn.recommendation = after["recommendation"]
            turn.allow_alternative = bool(after["allow_alternative"])
            span.set_attribute(
                "teams.card", turn.recommendation.get("track_id", "")
            )
        return turn


def new_correlation_id() -> str:
    return f"wc-{uuid.uuid4().hex[:12]}"
