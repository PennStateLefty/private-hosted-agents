"""Load the version-controlled track catalog and recommendation matrix.

The YAML files under ``catalog/`` are the single source of truth for tracks and
the deterministic recommendation rules. Everything is cached after first load.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import yaml

# catalog/ lives at the workload root: <root>/catalog/*.yaml
# This file is <root>/src/workshop_concierge/catalog.py -> parents[2] == <root>
_DEFAULT_CATALOG_DIR = Path(__file__).resolve().parents[2] / "catalog"


def _catalog_dir() -> Path:
    override = os.environ.get("WORKSHOP_CATALOG_DIR")
    return Path(override) if override else _DEFAULT_CATALOG_DIR


def _load_yaml(name: str) -> dict[str, Any]:
    path = _catalog_dir() / name
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"catalog file {path} did not parse to a mapping")
    return data


@functools.lru_cache(maxsize=1)
def load_tracks() -> dict[str, dict[str, str]]:
    """Return ``{track_id: {id,title,focus,summary}}``."""
    data = _load_yaml("tracks.yaml")
    tracks = {t["id"]: t for t in data["tracks"]}
    if not tracks:
        raise ValueError("no tracks defined in tracks.yaml")
    return tracks


@functools.lru_cache(maxsize=1)
def load_matrix() -> dict[str, Any]:
    """Return the parsed recommendation matrix."""
    return _load_yaml("recommendation_matrix.yaml")


def track(track_id: str) -> dict[str, str]:
    tracks = load_tracks()
    if track_id not in tracks:
        raise KeyError(f"unknown track '{track_id}'")
    return tracks[track_id]


def reset_cache() -> None:
    """Clear caches (used by tests that swap WORKSHOP_CATALOG_DIR)."""
    load_tracks.cache_clear()
    load_matrix.cache_clear()
