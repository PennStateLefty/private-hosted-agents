"""Unit tests for the deterministic recommendation rules (no LLM)."""
import itertools

import pytest

from workshop_concierge import recommend
from workshop_concierge.catalog import load_tracks

ROLES = ["Developer", "Architect", "Business leader"]
GOALS = ["Build an agent", "Integrate an agent", "Govern and operate agents"]

GOAL_TO_TRACK = {
    "Build an agent": "build",
    "Integrate an agent": "integrate",
    "Govern and operate agents": "govern",
}


@pytest.mark.parametrize("role,goal", list(itertools.product(ROLES, GOALS)))
def test_primary_track_is_driven_by_goal(role, goal):
    rec = recommend.recommend_track(role, goal)
    assert rec["track_id"] == GOAL_TO_TRACK[goal]
    assert rec["title"] == load_tracks()[rec["track_id"]]["title"]


@pytest.mark.parametrize("role,goal", list(itertools.product(ROLES, GOALS)))
def test_recommendation_is_complete_and_distinct(role, goal):
    rec = recommend.recommend_track(role, goal)
    assert rec["rationale"]
    assert rec["alternative_track_id"]
    # The alternative must differ from the primary.
    assert rec["alternative_track_id"] != rec["track_id"]
    assert rec["alternative_title"]


@pytest.mark.parametrize("role,goal", list(itertools.product(ROLES, GOALS)))
def test_determinism_same_inputs_same_output(role, goal):
    a = recommend.recommend_track(role, goal)
    b = recommend.recommend_track(role, goal)
    assert a == b


def test_excluded_track_changes_primary():
    # Developer + Build -> primary build. Excluding build must move primary off build.
    rec = recommend.recommend_track("Developer", "Build an agent", excluded_track="build")
    assert rec["track_id"] != "build"
    assert rec["alternative_track_id"] != rec["track_id"]


def test_alias_normalization():
    rec = recommend.recommend_track("dev", "build")
    assert rec["role"] == "developer"
    assert rec["goal"] == "build_agent"
    assert rec["track_id"] == "build"


@pytest.mark.parametrize("role", ["", "  ", "chef", None])
def test_invalid_role_raises(role):
    with pytest.raises(recommend.InvalidInputError):
        recommend.recommend_track(role, "Build an agent")


@pytest.mark.parametrize("goal", ["", "cook dinner", None])
def test_invalid_goal_raises(goal):
    with pytest.raises(recommend.InvalidInputError):
        recommend.recommend_track("Developer", goal)


def test_unknown_excluded_track_raises():
    with pytest.raises(recommend.InvalidInputError):
        recommend.recommend_track("Developer", "Build an agent", excluded_track="nope")


def test_all_role_goal_combinations_yield_known_tracks():
    tracks = set(load_tracks())
    for role, goal in itertools.product(ROLES, GOALS):
        rec = recommend.recommend_track(role, goal)
        assert rec["track_id"] in tracks
        assert rec["alternative_track_id"] in tracks
