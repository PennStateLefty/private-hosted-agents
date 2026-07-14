"""Test doubles: a scripted FakeLlm that exercises the real ADK tool path
without any network call.

The concierge flow is: user message -> model emits a `recommend_track`
function call -> ADK runs the tool -> model emits a final text answer. FakeLlm
reproduces exactly that two-step behavior by inspecting the request contents.
"""
from __future__ import annotations

import re
from typing import AsyncGenerator

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

_ROLE_PAT = re.compile(r"(developer|architect|business leader)", re.I)
_GOAL_PAT = re.compile(r"(build an agent|integrate an agent|govern and operate agents)", re.I)


def _latest_text(request: LlmRequest) -> str:
    for content in reversed(request.contents or []):
        for part in content.parts or []:
            if getattr(part, "text", None):
                return part.text
    return ""


def _has_tool_response(request: LlmRequest) -> bool:
    for content in request.contents or []:
        for part in content.parts or []:
            if getattr(part, "function_response", None) is not None:
                return True
    return False


class FakeLlm(BaseLlm):
    """A deterministic two-step stand-in for the Foundry model."""

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        if _has_tool_response(llm_request):
            # Second call: summarize the tool result as the final answer.
            track = "your recommended track"
            for content in llm_request.contents or []:
                for part in content.parts or []:
                    fr = getattr(part, "function_response", None)
                    if fr is not None and isinstance(fr.response, dict):
                        track = fr.response.get("track_id", track)
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=f"I recommend the '{track}' track. Accept?")],
                )
            )
            return

        # First call: extract role/goal from the user text and call the tool.
        text = " ".join(_latest_text(llm_request).split())
        role_m = _ROLE_PAT.search(text)
        goal_m = _GOAL_PAT.search(text)
        role = role_m.group(1) if role_m else "Developer"
        goal = goal_m.group(1) if goal_m else "Build an agent"
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            name="recommend_track",
                            args={"role": role, "goal": goal},
                        )
                    )
                ],
            )
        )
