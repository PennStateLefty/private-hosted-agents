"""Session-state schema and stage-transition rules for the Workshop Concierge.

Mirrors the ADK session state the agent keeps in ``tool_context.state`` /
``session.state`` so that the deterministic control flow (intake ->
recommendation -> at most one alternative -> confirmation) is unit-testable
without an LLM. The bounded loop (at most one alternative) is enforced here.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional

from . import recommend

MAX_ALTERNATIVES = 1


class Stage(str, enum.Enum):
    INTAKE = "intake"
    RECOMMENDED = "recommended"
    CONFIRMED = "confirmed"


class TransitionError(RuntimeError):
    """Raised when an action is not valid for the current stage."""


@dataclass
class ConciergeSession:
    """In-memory model of the concierge conversation state.

    Field names match the keys written to ADK session state so the two stay in
    sync (see ``STATE_KEYS``).
    """

    correlation_id: Optional[str] = None
    conversation_id: Optional[str] = None
    stage: Stage = Stage.INTAKE
    role: Optional[str] = None
    goal: Optional[str] = None
    recommendation: Optional[dict] = None
    alternative_count: int = 0
    final_track: Optional[str] = None
    next_action: Optional[str] = None
    history: list[str] = field(default_factory=list)

    # ---- transitions -------------------------------------------------

    def submit_intake(self, role: str, goal: str) -> dict:
        """Record the role/goal and produce the first recommendation."""
        if self.stage is Stage.CONFIRMED:
            raise TransitionError("session already confirmed; start over first")
        rec = recommend.recommend_track(role, goal)
        self.role = rec["role"]
        self.goal = rec["goal"]
        self.recommendation = rec
        self.alternative_count = 0
        self.stage = Stage.RECOMMENDED
        self.history.append(f"intake:{self.role}/{self.goal}")
        return rec

    def show_alternative(self) -> dict:
        """Produce the single bounded alternative recommendation."""
        if self.stage is not Stage.RECOMMENDED or self.recommendation is None:
            raise TransitionError("no active recommendation to replace")
        if self.alternative_count >= MAX_ALTERNATIVES:
            raise TransitionError(
                "alternative limit reached; accept a recommendation or start over"
            )
        current = self.recommendation["track_id"]
        rec = recommend.recommend_track(self.role, self.goal, excluded_track=current)
        self.recommendation = rec
        self.alternative_count += 1
        self.history.append(f"alternative:{rec['track_id']}")
        return rec

    def accept(self) -> str:
        """Confirm the currently recommended track."""
        if self.stage is not Stage.RECOMMENDED or self.recommendation is None:
            raise TransitionError("nothing to accept yet")
        self.final_track = self.recommendation["track_id"]
        self.stage = Stage.CONFIRMED
        # Intended next action is RECORDED only — no external registration.
        self.next_action = f"enroll_intent:{self.final_track}"
        self.history.append(f"accept:{self.final_track}")
        return self.final_track

    def start_over(self) -> None:
        self.stage = Stage.INTAKE
        self.role = None
        self.goal = None
        self.recommendation = None
        self.alternative_count = 0
        self.final_track = None
        self.next_action = None
        self.history.append("start_over")

    # ---- serialization ------------------------------------------------

    STATE_KEYS = (
        "stage",
        "role",
        "goal",
        "recommendation",
        "alternative_count",
        "final_track",
        "next_action",
        "correlation_id",
        "conversation_id",
    )

    def to_state(self) -> dict:
        out = {}
        for k in self.STATE_KEYS:
            v = getattr(self, k)
            out[k] = v.value if isinstance(v, Stage) else v
        return out

    @classmethod
    def from_state(cls, state: dict) -> "ConciergeSession":
        s = cls()
        for k in cls.STATE_KEYS:
            if k in state and state[k] is not None:
                setattr(s, k, state[k])
        if isinstance(s.stage, str):
            s.stage = Stage(s.stage)
        return s
