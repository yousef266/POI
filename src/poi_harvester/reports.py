"""Machine-readable source-policy and taxonomy coverage reports."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import json

from .sources import load_registry
from .taxonomy import catalog


def license_report(registry_path: Path) -> dict:
    entries = []
    for source in load_registry(registry_path):
        entries.append({
            "source": source["name"],
            "kind": source["kind"],
            "endpoint_or_path": source.get("endpoint") or source.get("path"),
            "auth_mode": source["auth_mode"],
            "license": source["license"],
            "attribution": source["attribution"],
            "allowed_use": sorted(source["allowed_uses"]),
            "commercial_use": source["commercial_use"],
            "redistribution": "redistribute" in source["allowed_uses"],
            "rate_limit_per_second": source["rate_limit_per_second"],
            "coverage_bbox": source.get("coverage_bbox"),
            "freshness": source["freshness"],
            "reliability_weight": source["reliability_weight"],
            "legal_approval": "NOT_CERTIFIED",
        })
    return {"status": "PASS", "source_count": len(entries), "sources": entries,
            "legal_approval": "NOT_CERTIFIED"}


def taxonomy_report(review_queue_path: Path | None = None) -> dict:
    leaves = catalog()["leaves"]
    if len({leaf["id"] for leaf in leaves}) != len(leaves) or len(leaves) != catalog()["leaf_count"]:
        raise ValueError("Taxonomy IDs/count are inconsistent")
    crosswalks = {
        "osm": "osm_tags", "google": "google_types",
        "wikidata": "wikidata_classes",
    }
    coverage = {}
    for provider, field in crosswalks.items():
        mapping: dict[str, set[str]] = defaultdict(set)
        for leaf in leaves:
            for value in leaf[field]:
                mapping[value].add(leaf["id"])
        coverage[provider] = {
            "mapping_count": len(mapping),
            "mapped_leaf_count": sum(bool(leaf[field]) for leaf in leaves),
            "leaf_coverage": round(sum(bool(leaf[field]) for leaf in leaves) / len(leaves), 4),
            "unmapped_leaf_ids": sorted(leaf["id"] for leaf in leaves if not leaf[field]),
            "ambiguous_mappings": {key: sorted(ids) for key, ids in sorted(mapping.items())
                                   if len(ids) > 1},
        }
    review = []
    if review_queue_path is not None:
        review = json.loads(review_queue_path.read_text(encoding="utf-8"))
    category_review = [item for item in review if any(
        word in item.get("reason", "").casefold() for word in
        ("category", "ambiguous osm tag", "unmapped"))]
    return {
        "status": "PASS", "leaf_count": len(leaves), "coverage": coverage,
        "review_queue_count": len(review),
        "unmapped_source_categories": sorted({str(item.get("record", {}).get("category")) for item in category_review
                                              if "unmapped" in item.get("reason", "").casefold()}),
        "source_category_review_count": len(category_review),
        "source_category_review": category_review,
        "official_category_accuracy": "NOT_CERTIFIED",
    }
