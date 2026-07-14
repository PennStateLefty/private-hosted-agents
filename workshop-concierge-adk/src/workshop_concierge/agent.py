"""The Workshop Concierge Google ADK agent.

A single ``LlmAgent`` coordinated with deterministic code:

* model  -- routed to a Foundry-deployed model through an OpenAI-compatible
            client (LiteLLM + Entra bearer token). No Gemini / Vertex / AI Studio.
* tool   -- the deterministic ``recommend_track`` FunctionTool.
* session state -- role, goal, recommendation, alternative_count, final choice.
* callbacks -- before/after hooks for validation, correlation, and trace
            enrichment (maps to OpenTelemetry / Application Insights).

Model construction is lazy and network-free at import time, so the agent object
and its tool wiring can be built and inspected offline. The actual model call
happens only when the agent runs.
"""
from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import urlparse

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from . import recommend
from .guardrail import before_model_callback as _guardrail_before_model
from .session import ConciergeSession

APP_NAME = "workshop-concierge"
DEFAULT_MODEL_DEPLOYMENT = "chat"  # gpt-5.4-mini (GlobalStandard) in the LZ
DEFAULT_API_VERSION = "2025-04-01-preview"

INSTRUCTION = """\
You are the Workshop Concierge. Help the attendee pick one of three workshop
tracks: Build, Integrate, or Govern.

Rules you must follow:
- Collect exactly two things: the attendee's ROLE (Developer, Architect, or
  Business leader) and their PRIMARY GOAL (Build an agent, Integrate an agent,
  or Govern and operate agents).
- You must NOT invent a recommendation yourself. Always call the
  `recommend_track` tool with the normalized role and goal; the tool decides the
  track. You may explain the tool's rationale in friendly language.
- When the attendee asks for the alternative, call `recommend_track` again with
  `excluded_track` set to the track you just recommended. Offer at most ONE
  alternative.
- When the attendee accepts, acknowledge the final track and state the intended
  next action ("record enrollment intent"). Do NOT claim to have registered them
  or updated any external system.
- Keep replies concise.
"""


# --------------------------------------------------------------------------- #
# Deterministic tool
# --------------------------------------------------------------------------- #
def recommend_track(
    role: str,
    goal: str,
    excluded_track: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Recommend a deterministic workshop track for a role and goal.

    Args:
        role: The attendee's role: "Developer", "Architect", or "Business leader".
        goal: The attendee's primary goal: "Build an agent", "Integrate an
            agent", or "Govern and operate agents".
        excluded_track: Optional track id to avoid, used only when the attendee
            asks to see the single alternative.

    Returns:
        A dict with track_id, title, rationale, alternative_track_id,
        alternative_title, and the normalized role/goal. On invalid input it
        returns {"error": <message>} instead of raising, so the model can ask a
        clarifying question.
    """
    try:
        rec = recommend.recommend_track(role, goal, excluded_track=excluded_track)
    except recommend.InvalidInputError as exc:
        return {"error": str(exc)}

    # Mirror the recommendation into ADK session state for correlation + the
    # bounded-loop control flow, matching ConciergeSession's schema.
    if tool_context is not None:
        state = tool_context.state
        state["role"] = rec["role"]
        state["goal"] = rec["goal"]
        state["recommendation"] = rec
        state["stage"] = "recommended"
        if excluded_track:
            state["alternative_count"] = int(state.get("alternative_count", 0)) + 1
        else:
            state.setdefault("alternative_count", 0)
        # Record an observable tool event marker for telemetry correlation.
        state["last_tool"] = "recommend_track"
    return rec


# --------------------------------------------------------------------------- #
# Callbacks: validation, correlation, trace enrichment
# --------------------------------------------------------------------------- #
def _before_agent(callback_context: CallbackContext) -> None:
    """Seed correlation + stage into session state before the turn runs."""
    state = callback_context.state
    if not state.get("correlation_id"):
        # Prefer a platform/adapter-provided correlation id; fall back to the
        # invocation id so every turn is still correlatable.
        state["correlation_id"] = (
            os.environ.get("WORKSHOP_CORRELATION_ID")
            or getattr(callback_context, "invocation_id", None)
        )
    state.setdefault("stage", "intake")
    state.setdefault("alternative_count", 0)


def _after_tool(
    tool: Any, args: dict, tool_context: ToolContext, tool_response: dict
) -> None:
    """Enrich the trace with the tool outcome (no secrets, no user PII)."""
    try:
        span = _current_span()
        if span is not None:
            span.set_attribute("workshop.tool.name", getattr(tool, "name", "recommend_track"))
            if isinstance(tool_response, dict) and "track_id" in tool_response:
                span.set_attribute("workshop.recommended_track", tool_response["track_id"])
            corr = tool_context.state.get("correlation_id")
            if corr:
                span.set_attribute("workshop.correlation_id", str(corr))
    except Exception:  # tracing must never break the agent
        pass


def _current_span():
    try:
        from opentelemetry import trace

        return trace.get_current_span()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Model factory: Foundry-deployed model via an OpenAI-compatible client
# --------------------------------------------------------------------------- #
def _derive_openai_endpoint() -> Optional[str]:
    """Derive the Azure OpenAI-compatible base URL from the Foundry endpoint.

    Prefers an explicit AZURE_OPENAI_ENDPOINT; otherwise derives the account
    host from FOUNDRY_PROJECT_ENDPOINT (platform-injected in the hosted agent).
    """
    explicit = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if explicit:
        return explicit.rstrip("/")
    project = os.environ.get("FOUNDRY_PROJECT_ENDPOINT") or os.environ.get(
        "AZURE_AI_PROJECT_ENDPOINT"
    )
    if not project:
        return None
    host = urlparse(project).netloc  # aif-...services.ai.azure.com
    if not host:
        return None
    return f"https://{host}"


def build_foundry_model():
    """Build a LiteLlm model routed to the Foundry-deployed model over Entra.

    Uses DefaultAzureCredential (the hosted agent identity in production; your
    az/azd login locally) — no keys, honoring disableLocalAuth on the account.
    """
    from google.adk.models.lite_llm import LiteLlm
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    deployment = os.environ.get("MODEL_DEPLOYMENT_NAME", DEFAULT_MODEL_DEPLOYMENT)
    api_base = _derive_openai_endpoint()
    if not api_base:
        raise RuntimeError(
            "No model endpoint configured. Set AZURE_OPENAI_ENDPOINT or "
            "FOUNDRY_PROJECT_ENDPOINT."
        )
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION)
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        os.environ.get(
            "AZURE_OPENAI_TOKEN_SCOPE", "https://cognitiveservices.azure.com/.default"
        ),
    )
    return LiteLlm(
        model=f"azure/{deployment}",
        api_base=api_base,
        api_version=api_version,
        azure_ad_token_provider=token_provider,
    )


# --------------------------------------------------------------------------- #
# Agent factory
# --------------------------------------------------------------------------- #
def create_agent(model: Any = None) -> LlmAgent:
    """Create the Workshop Concierge LlmAgent.

    Args:
        model: Optional model override (a BaseLlm or model-name str) for tests
            or local runs. When None, the Foundry model is built lazily.
    """
    resolved_model = model if model is not None else build_foundry_model()
    return LlmAgent(
        name="workshop_concierge",
        model=resolved_model,
        instruction=INSTRUCTION,
        description="Recommends a workshop track (Build/Integrate/Govern) from role and goal.",
        tools=[FunctionTool(recommend_track)],
        before_agent_callback=_before_agent,
        before_model_callback=_guardrail_before_model,
        after_tool_callback=_after_tool,
        output_key="last_response",
    )


def new_session_state(correlation_id: Optional[str] = None,
                      conversation_id: Optional[str] = None) -> dict:
    """Initial ADK session state seeded for a new conversation."""
    s = ConciergeSession(correlation_id=correlation_id, conversation_id=conversation_id)
    return s.to_state()

