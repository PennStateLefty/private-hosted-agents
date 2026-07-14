"""ADK runner wrapper used by the Responses adapter.

Maps a single non-streaming turn (conversation id + user text) onto an ADK
``Runner`` invocation, preserving conversation continuity by using the
Responses conversation id as the ADK session id. Session state is seeded with
the shared correlation id so tool events and telemetry line up.
"""
from __future__ import annotations

import inspect
from typing import Any, Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from workshop_concierge.agent import APP_NAME, create_agent, new_session_state


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class ConciergeRunner:
    """Owns the ADK agent + session service for the lifetime of the process."""

    def __init__(self, model: Any = None, app_name: str = APP_NAME,
                 user_id: str = "teams-user"):
        self.app_name = app_name
        self.user_id = user_id
        self.session_service = InMemorySessionService()
        self.agent = create_agent(model=model)
        self.runner = Runner(
            agent=self.agent,
            app_name=app_name,
            session_service=self.session_service,
        )

    async def _ensure_session(self, session_id: str, correlation_id: Optional[str],
                              conversation_id: Optional[str]) -> None:
        existing = await _maybe_await(
            self.session_service.get_session(
                app_name=self.app_name, user_id=self.user_id, session_id=session_id
            )
        )
        if existing is None:
            await _maybe_await(
                self.session_service.create_session(
                    app_name=self.app_name,
                    user_id=self.user_id,
                    session_id=session_id,
                    state=new_session_state(correlation_id, conversation_id),
                )
            )

    async def run_turn(self, conversation_id: Optional[str], text: str,
                       correlation_id: Optional[str] = None) -> str:
        """Run one turn and return the final assistant text.

        Raises ValueError on empty input so the adapter can surface an explicit
        non-success error.
        """
        if not text or not text.strip():
            raise ValueError("empty input: a user message is required")
        session_id = conversation_id or "default-session"
        await self._ensure_session(session_id, correlation_id, conversation_id)

        content = types.Content(role="user", parts=[types.Part(text=text)])
        final_text = ""
        async for event in self.runner.run_async(
            user_id=self.user_id, session_id=session_id, new_message=content
        ):
            if event.is_final_response() and getattr(event, "content", None):
                parts = event.content.parts or []
                final_text = "".join(p.text or "" for p in parts if getattr(p, "text", None))
        return final_text

    async def get_recommendation(
        self, conversation_id: Optional[str]
    ) -> Optional[dict]:
        """Return the recommendation the ``recommend_track`` tool wrote into session
        state, or ``None`` if the agent hasn't recommended a track yet.

        Shape: ``{"recommendation": <recommend_track dict>, "allow_alternative": bool}``.
        ``allow_alternative`` is False once the single bounded alternative has been
        shown (``alternative_count`` > 0), matching the deterministic card flow. Lets
        a caller render the shared recommendation Adaptive Card for the agent's turn.
        """
        session_id = conversation_id or "default-session"
        session = await _maybe_await(
            self.session_service.get_session(
                app_name=self.app_name, user_id=self.user_id, session_id=session_id
            )
        )
        if session is None:
            return None
        rec = session.state.get("recommendation")
        if not isinstance(rec, dict):
            return None
        alt_count = int(session.state.get("alternative_count", 0) or 0)
        return {"recommendation": dict(rec), "allow_alternative": alt_count == 0}
