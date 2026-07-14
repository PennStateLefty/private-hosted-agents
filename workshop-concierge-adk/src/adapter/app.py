"""Foundry Hosted Agent Responses adapter for the Workshop Concierge.

Exposes the ADK agent through the Azure AI Agent Server *Responses* protocol
(`azure-ai-agentserver-responses`). The protocol library serves `/responses`,
`/readiness`, cancellation, and the response lifecycle; this module implements
the create-response handler that maps a Responses request onto one ADK turn.

Run locally:
    python -m adapter.app          # serves on 0.0.0.0:8088
"""
from __future__ import annotations

import os
from typing import Any, Optional

from azure.ai.agentserver.responses import (
    ResponsesAgentServerHost,
    TextResponse,
    get_conversation_id,
)

from .adk_runner import ConciergeRunner

PORT = int(os.environ.get("PORT", "8088"))


def _extract_correlation(request: Any, conversation_id: Optional[str]) -> Optional[str]:
    """Prefer an explicit correlation id from request metadata, else the
    conversation id, so every turn is correlatable end-to-end."""
    meta = getattr(request, "metadata", None)
    if isinstance(meta, dict):
        for key in ("correlation_id", "x-correlation-id", "correlationId"):
            if meta.get(key):
                return str(meta[key])
    return conversation_id


def create_app(runner: Optional[ConciergeRunner] = None) -> ResponsesAgentServerHost:
    """Build the Responses host. ``runner`` can be injected for tests."""
    app = ResponsesAgentServerHost()
    holder: dict[str, Optional[ConciergeRunner]] = {"runner": runner}

    def get_runner() -> ConciergeRunner:
        if holder["runner"] is None:
            holder["runner"] = ConciergeRunner()
        return holder["runner"]

    @app.response_handler
    def handle(request, context, cancellation_signal):
        async def produce() -> str:
            text = await context.get_input_text()
            conversation_id = get_conversation_id(request)
            correlation_id = _extract_correlation(request, conversation_id)
            reply = await get_runner().run_turn(
                conversation_id, text, correlation_id=correlation_id
            )
            return reply or "(the concierge produced no text this turn)"

        return TextResponse(context, request, text=produce)

    return app


app = None


def main() -> None:
    global app
    app = create_app()
    app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
