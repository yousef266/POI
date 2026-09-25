"""Pairwise conflation and field-provenance evaluation against explicit labels."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
import json


def evaluate_conflation(records_path: Path, gold_path: Path | None = None) -> dict:
    if gold_path is None:
        return {"status": "NOT_CERTIFIED", "reason": "No labelled gold dataset supplied"}
    records = json.loads(records_path.read_text(encoding="utf-8"))
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    labels = {item["source_key"]: item["entity_id"] for item in gold["entities"]}
    if len(labels) != len(gold["entities"]):
        raise ValueError("Gold data contains duplicate source keys")
    predicted_keys = {key for row in records for key in row["source_keys"]}
    unlabeled = predicted_keys - labels.keys()
    if unlabeled:
        raise ValueError(f"Predicted source keys have no gold label: {sorted(unlabeled)}")
    predicted_pairs = {tuple(sorted(pair)) for row in records
                       for pair in combinations(row["source_keys"], 2)}
    by_entity: dict[str, list[str]] = {}
    for key, entity in labels.items():
        by_entity.setdefault(entity, []).append(key)
    gold_pairs = {tuple(sorted(pair)) for keys in by_entity.values()
                  for pair in combinations(keys, 2)}
    true_pairs = predicted_pairs & gold_pairs
    false_merges = [list(pair) for pair in sorted(predicted_pairs - gold_pairs)]
    missed_merges = [list(pair) for pair in sorted(gold_pairs - predicted_pairs)]
    precision = len(true_pairs) / len(predicted_pairs) if predicted_pairs else (1.0 if not gold_pairs else 0.0)
    recall = len(true_pairs) / len(gold_pairs) if gold_pairs else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    by_source_key = {key: row for row in records for key in row["source_keys"]}
    field_checks = []
    for item in gold.get("field_truth", []):
        row = by_source_key.get(item["source_key"])
        actual = row.get("provenance", {}).get(item["field"]) if row else None
        field_checks.append({**item, "actual_source_key": actual,
                             "correct": actual == item["expected_source_key"]})
    correct_fields = sum(item["correct"] for item in field_checks)
    return {
        "status": "PASS", "gold_dataset": str(gold_path),
        "official_status": "NOT_CERTIFIED",
        "true_merge_pairs": len(true_pairs),
        "false_merge_pairs": false_merges,
        "missed_merge_pairs": missed_merges,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "field_provenance": {
            "correct": correct_fields, "total": len(field_checks),
            "accuracy": round(correct_fields / len(field_checks), 6) if field_checks else None,
            "checks": field_checks,
        },
    }
