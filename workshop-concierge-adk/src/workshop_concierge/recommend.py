"""Deterministic ``recommend_track`` tool and input normalization.

This module contains **no LLM calls**. The model explains the recommendation to
the user, but the track selection is a pure function of (role, goal) over the
version-controlled recommendation matrix, so results are reproducible and
evaluable.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

from . import catalog


class InvalidInputError(ValueError):
    """Raised when a role or goal cannot be normalized to a canonical value."""


@dataclass(frozen=True)
class Recommendation:
    track_id: str
    title: str
    rationale: str
    alternative_track_id: str
    alternative_title: str
    role: str
    goal: str
    excluded_track: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


def _normalize(value: str, aliases: dict[str, str], kind: str) -> str:
    if value is None:
        raise InvalidInputError(f"{kind} is required")
    key = str(value).strip().lower()
    if not key:
        raise InvalidInputError(f"{kind} is required")
    # Direct canonical value?
    if key in aliases.values():
        return key
    if key in aliases:
        return aliases[key]
    raise InvalidInputError(
        f"unrecognized {kind} '{value}'. Expected one of: "
        f"{sorted(set(aliases.values()))}"
    )


def normalize_role(role: str) -> str:
    matrix = catalog.load_matrix()
    return _normalize(role, matrix["role_aliases"], "role")


def normalize_goal(goal: str) -> str:
    matrix = catalog.load_matrix()
    return _normalize(goal, matrix["goal_aliases"], "goal")


def _rationale(role: str, goal: str, track_id: str) -> str:
    t = catalog.track(track_id)
    role_label = role.replace("_", " ")
    goal_label = goal.replace("_", " ")
    return (
        f"As a {role_label} whose primary goal is to {goal_label.replace('_', ' ')}, "
        f"the {t['title'].split(' — ')[0]} track is the best fit because it centers on "
        f"{t['focus'].lower()}."
    )


def recommend_track(role: str, goal: str, excluded_track: Optional[str] = None) -> dict:
    """Return a deterministic track recommendation.

    Args:
        role: user role (Developer / Architect / Business leader, or an alias).
        goal: primary goal (Build / Integrate / Govern an agent, or an alias).
        excluded_track: a track id to avoid, used for the single bounded
            "show me an alternative" request.

    Returns:
        A dict with track_id, title, rationale, alternative_track_id,
        alternative_title, plus the normalized role/goal and excluded_track.

    Raises:
        InvalidInputError: if role or goal cannot be normalized.
    """
    norm_role = normalize_role(role)
    norm_goal = normalize_goal(goal)
    matrix = catalog.load_matrix()

    excluded = None
    if excluded_track:
        excluded = str(excluded_track).strip().lower()
        if excluded not in catalog.load_tracks():
            raise InvalidInputError(f"unknown excluded_track '{excluded_track}'")

    affinity: list[str] = list(matrix["role_affinity"][norm_role])
    natural = matrix["goal_to_track"][norm_goal]

    # Primary track: the goal's natural track, unless it is excluded.
    if excluded and natural == excluded:
        primary = next(t for t in affinity if t != excluded)
    else:
        primary = natural

    # Alternative: highest role-affinity track that is neither primary nor excluded.
    alternative = next(
        (t for t in affinity if t != primary and t != excluded),
        # Degenerate fallback: any other track.
        next(t for t in catalog.load_tracks() if t != primary),
    )

    primary_track = catalog.track(primary)
    alt_track = catalog.track(alternative)

    return Recommendation(
        track_id=primary,
        title=primary_track["title"],
        rationale=_rationale(norm_role, norm_goal, primary),
        alternative_track_id=alternative,
        alternative_title=alt_track["title"],
        role=norm_role,
        goal=norm_goal,
        excluded_track=excluded,
    ).as_dict()
