"""Adaptive Card builders for the Workshop Concierge (schema 1.5).

Two cards:
* intake card       -- collects Role + Primary goal (Action.Submit).
* recommendation card -- shows the recommended track with Accept / Show
                        alternative / Start over actions.

Every card carries the shared correlation id in its Action.Submit ``data`` so
the submitted values can be correlated end-to-end in telemetry.
"""
from __future__ import annotations

from typing import Optional

from . import catalog

ADAPTIVE_CARD_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
ADAPTIVE_CARD_VERSION = "1.5"

ROLE_CHOICES = [
    {"title": "Developer", "value": "Developer"},
    {"title": "Architect", "value": "Architect"},
    {"title": "Business leader", "value": "Business leader"},
]

GOAL_CHOICES = [
    {"title": "Build an agent", "value": "Build an agent"},
    {"title": "Integrate an agent", "value": "Integrate an agent"},
    {"title": "Govern and operate agents", "value": "Govern and operate agents"},
]


def _card(body: list, actions: list) -> dict:
    return {
        "type": "AdaptiveCard",
        "$schema": ADAPTIVE_CARD_SCHEMA,
        "version": ADAPTIVE_CARD_VERSION,
        "body": body,
        "actions": actions,
    }


def intake_card(correlation_id: str) -> dict:
    """Card that collects role + goal."""
    body = [
        {"type": "TextBlock", "text": "Workshop Concierge", "weight": "Bolder", "size": "Large"},
        {"type": "TextBlock", "text": "Tell me about you and I'll recommend a track.", "wrap": True},
        {"type": "TextBlock", "text": "Your role", "weight": "Bolder"},
        {
            "type": "Input.ChoiceSet",
            "id": "role",
            "style": "expanded",
            "isRequired": True,
            "errorMessage": "Please choose a role.",
            "choices": ROLE_CHOICES,
        },
        {"type": "TextBlock", "text": "Your primary goal", "weight": "Bolder"},
        {
            "type": "Input.ChoiceSet",
            "id": "goal",
            "style": "expanded",
            "isRequired": True,
            "errorMessage": "Please choose a goal.",
            "choices": GOAL_CHOICES,
        },
    ]
    actions = [
        {
            "type": "Action.Submit",
            "title": "Recommend a track",
            "data": {"action": "submit_intake", "correlation_id": correlation_id},
        }
    ]
    return _card(body, actions)


def recommendation_card(recommendation: dict, correlation_id: str,
                        allow_alternative: bool = True) -> dict:
    """Card that presents a recommendation with Accept/Alternative/Start over."""
    track_id = recommendation["track_id"]
    alt_id = recommendation["alternative_track_id"]
    body = [
        {"type": "TextBlock", "text": "Recommended track", "weight": "Bolder", "size": "Medium"},
        {"type": "TextBlock", "text": recommendation["title"], "weight": "Bolder", "wrap": True},
        {"type": "TextBlock", "text": recommendation["rationale"], "wrap": True},
        {
            "type": "TextBlock",
            "text": f"Alternative: {recommendation['alternative_title']}",
            "isSubtle": True,
            "wrap": True,
        },
    ]
    actions = [
        {
            "type": "Action.Submit",
            "title": "Accept recommendation",
            "data": {
                "action": "accept",
                "track_id": track_id,
                "correlation_id": correlation_id,
            },
        }
    ]
    if allow_alternative:
        actions.append(
            {
                "type": "Action.Submit",
                "title": "Show alternative",
                "data": {
                    "action": "show_alternative",
                    "excluded_track": track_id,
                    "suggested_track": alt_id,
                    "correlation_id": correlation_id,
                },
            }
        )
    actions.append(
        {
            "type": "Action.Submit",
            "title": "Start over",
            "data": {"action": "start_over", "correlation_id": correlation_id},
        }
    )
    return _card(body, actions)


def validate_catalog_alignment() -> None:
    """Sanity-check that card choices match the catalog's known tracks."""
    tracks = set(catalog.load_tracks())
    assert tracks == {"build", "integrate", "govern"}, tracks
