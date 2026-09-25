"""Versioned canonical POI taxonomy and source-category crosswalks."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
import json


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads(files("poi_harvester").joinpath("taxonomy.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def by_id() -> dict[str, dict]:
    return {leaf["id"]: leaf for leaf in catalog()["leaves"]}


@lru_cache(maxsize=1)
def osm_crosswalk() -> dict[str, str]:
    return {tag: leaf["id"] for leaf in catalog()["leaves"] for tag in leaf["osm_tags"]}


@lru_cache(maxsize=1)
def google_crosswalk() -> dict[str, str]:
    return {place_type: leaf["id"] for leaf in catalog()["leaves"] for place_type in leaf["google_types"]}


@lru_cache(maxsize=1)
def wikidata_crosswalk() -> dict[str, str]:
    candidates: dict[str, set[str]] = {}
    for leaf in catalog()["leaves"]:
        for qid in leaf["wikidata_classes"]:
            candidates.setdefault(qid, set()).add(leaf["id"])
    return {qid: next(iter(categories)) for qid, categories in candidates.items() if len(categories) == 1}
