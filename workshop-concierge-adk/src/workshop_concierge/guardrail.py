"""Deterministic input guardrail for the Workshop Concierge.

Architecture-preserving: implemented as an ADK ``before_model_callback`` so a
blocked turn short-circuits BEFORE any model call and returns a fixed, safe
refusal that re-anchors the attendee to the concierge's only task (choosing a
workshop track). The guardrail is a pure function over the latest user text, so
it is fully unit-testable offline and behaves identically on the deployed agent.

Blocked categories (conservative, to avoid false positives on legitimate
role/goal inputs):

* ``instruction_override`` -- attempts to override, ignore, or replace the
  agent's instructions / persona (classic prompt injection / jailbreak).
* ``system_exfiltration`` -- attempts to reveal or echo the system prompt,
  instructions, or hidden rules.
* ``off_scope_task`` -- requests to perform unrelated generation/execution
  (write code, tell a joke, translate, etc.) that are outside the concierge's
  single responsibility.

A blocked turn sets ``guardrail_triggered``/``guardrail_reason`` in session state
and a ``workshop.guardrail.*`` span attribute for observability/correlation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

REFUSAL = (
    "I can only help you choose a workshop track: Build, Integrate, or Govern. "
    "I can't change my instructions, reveal internal configuration, or do "
    "unrelated tasks. To get a recommendation, tell me your role (Developer, "
    "Architect, or Business leader) and your primary goal (Build an agent, "
    "Integrate an agent, or Govern and operate agents)."
)

# Each pattern is deliberately specific so normal role/goal phrasing never trips
# it. Ordered by category; the first match wins and names the reason.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "instruction_override",
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass)\b[^.]*\b"
            r"(instruction|instructions|rule|rules|prompt|guardrail|guidelines|above|previous|prior|system)\b",
            re.I,
        ),
    ),
    (
        "instruction_override",
        re.compile(
            r"\b(you are now|from now on you are|act as|pretend to be|"
            r"developer mode|jailbreak|\bdan\b|do anything now|"
            r"roleplay as|behave as if)\b",
            re.I,
        ),
    ),
    (
        "system_exfiltration",
        re.compile(
            r"\b(reveal|show|print|repeat|output|echo|reprint|display|tell me)\b[^.]*\b"
            r"(system prompt|your prompt|your instructions|your rules|the text above|"
            r"hidden (prompt|instructions)|initial prompt)\b",
            re.I,
        ),
    ),
    (
        "system_exfiltration",
        re.compile(r"\bwhat (are|were) your (instructions|rules|system prompt)\b", re.I),
    ),
    (
        "off_scope_task",
        re.compile(
            r"\b(write|compose|generate|create|draft)\b[^.]*\b"
            r"(poem|song|story|essay|joke|python|javascript|code|script|program|"
            r"sql|shell command|malware|virus|email|resume)\b",
            re.I,
        ),
    ),
    (
        "off_scope_task",
        re.compile(
            r"\b(translate|weather|stock price|recipe|tell me a joke|"
            r"summarize this|solve this equation|do my homework)\b",
            re.I,
        ),
    ),
]


@dataclass(frozen=True)
class GuardrailVerdict:
    blocked: bool
    reason: Optional[str] = None
    message: Optional[str] = None


def screen(text: Optional[str]) -> GuardrailVerdict:
    """Screen a single user utterance. Pure, deterministic, offline-safe."""
    if not text:
        return GuardrailVerdict(blocked=False)
    for reason, pattern in _RULES:
        if pattern.search(text):
            return GuardrailVerdict(blocked=True, reason=reason, message=REFUSAL)
    return GuardrailVerdict(blocked=False)


def _latest_user_text(llm_request: Any) -> str:
    """Extract the most recent user text from an ADK LlmRequest."""
    contents = getattr(llm_request, "contents", None) or []
    for content in reversed(contents):
        role = getattr(content, "role", None)
        if role not in (None, "user"):
            continue
        parts = getattr(content, "parts", None) or []
        chunks = [getattr(p, "text", None) for p in parts]
        text = " ".join(c for c in chunks if c)
        if text.strip():
            return text
    return ""


def before_model_callback(callback_context: Any, llm_request: Any) -> Optional[Any]:
    """ADK before_model hook: block-and-refuse before any model call.

    Returns an ``LlmResponse`` (short-circuit) when the input is blocked, else
    ``None`` so the normal model call proceeds.
    """
    text = _latest_user_text(llm_request)
    verdict = screen(text)
    if not verdict.blocked:
        return None

    # Observable markers for correlation / telemetry (never raise).
    try:
        state = callback_context.state
        state["guardrail_triggered"] = True
        state["guardrail_reason"] = verdict.reason
    except Exception:  # pragma: no cover - defensive
        pass
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is not None:
            span.set_attribute("workshop.guardrail.triggered", True)
            span.set_attribute("workshop.guardrail.reason", verdict.reason or "")
    except Exception:  # pragma: no cover - tracing must never break the agent
        pass

    from google.adk.models import LlmResponse
    from google.genai import types

    return LlmResponse(
        content=types.Content(
            role="model", parts=[types.Part(text=verdict.message or REFUSAL)]
        ),
    )
