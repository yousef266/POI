"""Offline local acceptance suite with explicit official-certification boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys

from .conflation_eval import evaluate_conflation
from .core import Area, Request
from .pipeline import replay, reprocess_capture, run
from .reports import license_report, taxonomy_report


ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def _criterion(local_status: str, evidence: str, blocker: str) -> dict:
    return {"local_status": local_status, "official_status": "NOT_CERTIFIED",
            "evidence": evidence, "remaining_blocker": blocker}


def evaluate_local(output_dir: Path, registry_path: Path | None = None,
                   readiness_path: Path | None = None) -> dict:
    """Run fixture tests and local probes without external network access."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_path = (registry_path or ROOT / "sources.json").resolve()
    unit = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
                          cwd=ROOT, capture_output=True, text=True, timeout=120)
    fixture_dir = output_dir / "fixture"
    fixture = run(Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal"),
                  registry_path, fixture_dir, {"demo", "demo_alt"})
    fixture_replay = replay(fixture_dir)
    fixture_gold = evaluate_conflation(fixture_dir / "records.json",
                                       ROOT / "fixtures" / "conflation_gold.json")
    policy = license_report(registry_path)
    taxonomy = taxonomy_report(fixture_dir / "review_queue.json")
    benchmark = subprocess.run([sys.executable, str(ROOT / "scripts" / "benchmark_agent1.py")],
                               cwd=ROOT, capture_output=True, text=True, timeout=120)
    speed = json.loads(benchmark.stdout) if benchmark.returncode == 0 else None
    zurich_dir = ROOT / "output" / "zurich-mixed-corrected"
    zurich = None
    if (zurich_dir / "raw.json").exists():
        preview_dir = output_dir / "zurich_enriched"
        preview = reprocess_capture(zurich_dir, preview_dir)
        zurich = {"count": preview["feature_count"],
                  "bilingual_complete": preview["metadata"]["bilingual_complete_count"],
                  "exact_replay": replay(preview_dir)["identical"],
                  "human_name_quality": "NOT_CERTIFIED"}
    fixture_complete = fixture["metadata"]["bilingual_complete_count"]
    checks_pass = unit.returncode == 0
    local_replay = fixture_replay["identical"] and (zurich is None or zurich["exact_replay"])
    criteria = {
        "A1": _criterion("PASS" if checks_pass else "FAIL",
                         "Source denial tests and declared-policy report; OSM remains internal only",
                         "Official benchmark and operator/legal validation"),
        "A2": _criterion("PASS" if checks_pass else "FAIL",
                         "Four-process local rate test, robots denial, Retry-After, backoff and 304 tests",
                         "Official source load test and deployment environment"),
        "A3": _criterion("PASS" if checks_pass else "FAIL",
                         "Fixture field/metadata attribution tests; local published layers checked separately",
                         "Official benchmark attribution audit"),
        "A4": _criterion("PASS" if fixture_gold["precision"] >= 0.92 else "FAIL",
                         f"Project fixture pairwise precision {fixture_gold['precision']}",
                         "Official labelled Riyadh and held-out AOI"),
        "A5": _criterion("PASS" if fixture_gold["recall"] >= 0.85 else "FAIL",
                         f"Project fixture pairwise recall {fixture_gold['recall']}",
                         "Official labelled Riyadh and held-out AOI"),
        "A6": _criterion("NOT_CERTIFIED", "Taxonomy/crosswalk coverage reported without gold labels",
                         "Official category gold labels"),
        "A7": _criterion("PASS" if fixture_complete == fixture["feature_count"] and
                         (zurich is None or zurich["bilingual_complete"] == zurich["count"]) else "FAIL",
                         f"Fixture {fixture_complete}/{fixture['feature_count']} bilingual; " +
                         (f"captured Zurich {zurich['bilingual_complete']}/{zurich['count']}" if zurich else
                          "Zurich capture unavailable"),
                         "Official corpus and human review of generated names"),
        "A8": _criterion("NOT_CERTIFIED", "No 100-name human-rated Arabic sample",
                         "Human review sample"),
        "A9": _criterion("NOT_CERTIFIED", "Captured OSM coordinates are preserved locally",
                         "Gold source-of-truth coordinates"),
        "A10": _criterion("PASS" if checks_pass else "FAIL",
                          "Unit fixture classified 50 adds, 50 updates, 20 removals and 30 unchanged",
                          "Official seeded change set"),
        "A11": _criterion("PASS" if speed and speed["features_per_hour"] >= 10_000 else "FAIL",
                          f"Synthetic local rate {speed['features_per_hour'] if speed else 'unavailable'} POIs/hour",
                          "Official 4-vCPU/8-GB source workload"),
        "A12": _criterion("PASS" if local_replay else "FAIL",
                          "Fixture and saved Zurich capture reproduce exact merged output without LLM",
                          "Official full provenance replay corpus"),
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite": "local_offline",
        "unit_tests": {"status": "PASS" if checks_pass else "FAIL",
                       "exit_code": unit.returncode, "output": (unit.stderr + unit.stdout).strip()},
        "license_report": policy,
        "taxonomy_report": taxonomy,
        "fixture_conflation": fixture_gold,
        "fixture_exact_replay": fixture_replay,
        "synthetic_throughput": speed or {"status": "FAIL", "output": benchmark.stderr},
        "zurich_capture": zurich or {"status": "NOT_AVAILABLE"},
        "common_agent_contract": "NOT_AVAILABLE",
        "criteria": criteria,
    }
    _write(output_dir / "report.json", report)
    _write(output_dir / "license_report.json", policy)
    _write(output_dir / "taxonomy_report.json", taxonomy)
    if readiness_path is not None:
        lines = ["# Agent 1 submission readiness", "",
                 "Generated from the local offline evaluator. Local fixture results are not official bounty scores.",
                 "", "| Criterion | Local status | Official status | Evidence | Remaining blocker |",
                 "| --- | --- | --- | --- | --- |"]
        for name, item in criteria.items():
            lines.append("| " + " | ".join([name, item["local_status"], item["official_status"],
                                            item["evidence"], item["remaining_blocker"]]) + " |")
        lines.extend(["", "## Additional blockers", "",
                      "- The Common Agent Contract is unavailable; see CONTRACT_BLOCKER.md.",
                      "- Source license declarations require operator validation.",
                      "- Low-confidence generated Arabic names require human review.",
                      "- The official gold labels and specified benchmark hardware are unavailable.", ""])
        readiness_path.parent.mkdir(parents=True, exist_ok=True)
        readiness_path.write_text("\n".join(lines), encoding="utf-8")
    return report
