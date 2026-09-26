"""Deterministic project-authored incremental refresh probe with observable counts."""

from pathlib import Path
import json

from .audit import canonical_hash
from .core import Area, Request
from .pipeline import replay, run


def incremental_probe(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    def point(index, phone="100"):
        return {"id": str(index), "lat": 10 + index * 0.01, "lon": 20.0,
                "category": "pharmacy", "name_en": f"Pharmacy {index}", "phone": phone}
    source = {"name": "seed", "kind": "fixture", "path": "source.json",
              "license": "Project-authored synthetic changes", "allowed_uses": ["internal"],
              "commercial_use": False, "auth_mode": "none", "coverage_bbox": None,
              "freshness": "synthetic fixture", "attribution": "Project-authored synthetic changes",
              "rate_limit_per_second": 1, "reliability_weight": 0.9}
    registry, source_file = root / "registry.json", root / "source.json"
    registry.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
    source_file.write_text(json.dumps([point(index) for index in range(100)]), encoding="utf-8")
    request = Request(Area(9.9, 19.9, 12.0, 20.1), "pharmacy", "internal")
    run(request, registry, root / "first", {"seed"})
    changed = [point(index, "200" if index < 50 else "100") for index in range(80)]
    changed.extend(point(index) for index in range(100, 150))
    source_file.write_text(json.dumps(changed), encoding="utf-8")
    for directory in ("second", "repeated"):
        run(request, registry, root / directory, {"seed"}, root / "first" / "records.json")
    changes = json.loads((root / "second" / "changes.json").read_text(encoding="utf-8"))
    repeated = json.loads((root / "repeated" / "changes.json").read_text(encoding="utf-8"))
    counts = {key: len(changes[key]) for key in ("added", "updated", "removed", "unchanged")}
    expected = {"added": 50, "updated": 50, "removed": 20, "unchanged": 30}
    field_diff = all("phone" in row["changed_fields"] for row in changes["updated"])
    identical = canonical_hash(changes) == canonical_hash(repeated)
    replays = [replay(root / "second"), replay(root / "second")]
    passed = counts == expected and field_diff and identical and all(row["identical"] for row in replays)
    return {"status": "PASS" if passed else "FAIL", "dataset_kind": "project_authored_fixture",
            "counts": counts, "expected_counts": expected, "field_phone_diffs_verified": field_diff,
            "repeated_change_set_identical": identical, "change_set_hash": canonical_hash(changes),
            "replay_checks": replays, "official_status": "NOT_CERTIFIED"}
