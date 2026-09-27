"""Local acceptance evidence with explicit official-certification boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import json
import re
import subprocess
import sys

from .conflation_eval import evaluate_conflation
from .core import Area, Request
from .name_review import score_reviews
from .pipeline import replay, reprocess_capture, run
from .reports import license_report, taxonomy_report
from .validation import incremental_probe
from .config import load_env_file
from .publish import verify_local

def _submission_root() -> Path:
    for candidate in (Path.cwd(), Path(__file__).resolve().parents[2]):
        if (candidate / "sources.json").exists() and (candidate / "tests").is_dir() and (candidate / "scripts").is_dir():
            return candidate.resolve()
    return Path(__file__).resolve().parents[2]


ROOT = _submission_root()


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _criterion(local_status: str, evidence: str, blocker: str, command: str | None, output) -> dict:
    return {"local_status": local_status, "official_status": "NOT_CERTIFIED",
            "evidence": evidence, "remaining_blocker": blocker, "command": command, "output": output}


def _throughput_criterion(speed, command):
    """A grid load probe cannot certify real, correctly located POI harvesting."""
    probe_passed = bool(speed and speed['complete_features_per_hour'] >= 10_000)
    return _criterion('NOT_CERTIFIED' if probe_passed else 'FAIL',
                      'Synthetic grid load test only; invented locations, no real source harvest or accuracy evidence',
                      'Real benchmark POIs with reference geometry and the required 4-vCPU/8-GB environment',
                      command, speed)


def evaluate_local(output_dir: Path, registry_path: Path | None = None,
                   readiness_path: Path | None = None, publication_target: dict | None = None,
                   env_file: Path | None = None, ratings_path: Path | None = None) -> dict:
    """Offline by default; publication is opt-in and uses the configured services."""
    if not (ROOT / "tests").is_dir() or not (ROOT / "scripts" / "benchmark_agent1.py").exists():
        raise ValueError("Evaluation requires the submission checkout with tests/scripts/fixtures; run from its root")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_path = (registry_path or ROOT / "sources.json").resolve()
    unit_started = perf_counter()
    unit = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                          cwd=ROOT, capture_output=True, text=True, timeout=180)
    unit_seconds = perf_counter() - unit_started
    unit_log = unit.stderr + unit.stdout
    (output_dir / "tests.log").write_text(unit_log, encoding="utf-8")
    tests_match = re.search(r"Ran (\d+) tests?", unit_log)
    tests_count = int(tests_match.group(1)) if tests_match else 0
    skipped_match = re.search(r"skipped=(\d+)", unit_log)
    skipped = int(skipped_match.group(1)) if skipped_match else 0
    failed_match = re.search(r"failures=(\d+)", unit_log)
    errors_match = re.search(r"errors=(\d+)", unit_log)
    failed = (int(failed_match.group(1)) if failed_match else 0) + (int(errors_match.group(1)) if errors_match else 0)
    tests = {"status": "PASS" if unit.returncode == 0 and tests_count else "FAIL",
             "command": "python -m unittest discover -s tests -v", "exit_code": unit.returncode,
             "tests": tests_count, "passed": tests_count - failed - skipped, "failed": failed,
             "skipped": skipped, "runtime_seconds": round(unit_seconds, 6),
             "output": unit_log.strip()}
    fixture_dir = output_dir / "fixture"
    fixture = run(Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal"),
                  registry_path, fixture_dir, {"demo", "demo_alt"})
    fixture_replays = [replay(fixture_dir), replay(fixture_dir)]
    fixture_gold = evaluate_conflation(fixture_dir / "records.json", ROOT / "fixtures" / "conflation_gold.json")
    policy = license_report(registry_path)
    taxonomy = taxonomy_report(fixture_dir / "review_queue.json")
    incremental = incremental_probe(output_dir / "incremental")
    review_dataset = json.loads((ROOT / "fixtures" / "arabic_name_review.json").read_text(encoding="utf-8"))
    review_ratings = json.loads(ratings_path.read_text(encoding="utf-8")) if ratings_path else None
    name_review = score_reviews(review_dataset, review_ratings)
    _write(output_dir / "arabic_review_score.json", name_review)
    benchmark_args = ["--out", str(output_dir / "benchmark")]
    if publication_target:
        if not publication_target.get("database") or not publication_target.get("workspace"):
            raise ValueError("Local services evaluation requires --database and --workspace")
        benchmark_args.extend(["--publish", "--database", publication_target["database"],
                               "--schema", publication_target["schema"], "--workspace", publication_target["workspace"]])
        if env_file:
            benchmark_args.extend(["--env-file", str(env_file.resolve())])
    benchmark = subprocess.run([sys.executable, str(ROOT / "scripts" / "benchmark_agent1.py"), *benchmark_args],
                               cwd=ROOT, capture_output=True, text=True, timeout=240)
    (output_dir / "benchmark.log").write_text(benchmark.stdout + benchmark.stderr, encoding="utf-8")
    speed = json.loads(benchmark.stdout) if benchmark.returncode == 0 else None
    benchmark_command = "python scripts/benchmark_agent1.py --out " + str(output_dir.relative_to(ROOT) if output_dir.is_relative_to(ROOT) else output_dir) + "/benchmark"
    if publication_target:
        benchmark_command += (" --publish --database " + publication_target["database"] +
                              " --schema " + publication_target["schema"] + " --workspace " + publication_target["workspace"])
        if env_file:
            benchmark_command += " --env-file " + str(env_file)
    zurich_dir = ROOT / "output" / "zurich-mixed-corrected"
    zurich = {"status": "NOT_AVAILABLE"}
    if (zurich_dir / "raw.json").exists():
        preview_dir = output_dir / "zurich_enriched"
        prior_records = json.loads((zurich_dir / "records.json").read_text(encoding="utf-8"))
        preview = reprocess_capture(zurich_dir, preview_dir)
        records = json.loads((preview_dir / "records.json").read_text(encoding="utf-8"))
        prior_points = {row["stable_id"]: (row["lon"], row["lat"]) for row in prior_records}
        new_points = {row["stable_id"]: (row["lon"], row["lat"]) for row in records}
        checks = [replay(preview_dir), replay(preview_dir)]
        historical = [replay(zurich_dir), replay(zurich_dir)]
        zurich = {"status": "PASS" if prior_points == new_points and all(row["identical"] for row in checks + historical) else "FAIL",
                  "count": preview["feature_count"], "baseline_count": len(prior_records),
                  "stable_ids_and_coordinates_preserved": prior_points == new_points,
                  "bilingual_complete": preview["metadata"]["bilingual_complete_count"],
                  "exact_replay": all(row["identical"] for row in checks + historical),
                  "replay_checks": checks, "historical_replay_checks": historical,
                  "human_name_quality": "NOT_CERTIFIED"}
    saved_layers = {}
    if publication_target:
        load_env_file(env_file)
        for name in ("zurich-mixed-corrected", "zurich-osm-real", "zurich-bakeries-real", "evaluation/zurich_enriched"):
            saved_dir = ROOT / "output" / name
            publication_path = saved_dir / "publication.json"
            if not publication_path.exists():
                continue
            target = json.loads(publication_path.read_text(encoding="utf-8"))
            if target["database"] != publication_target["database"]:
                continue
            workspace, layer = target["layer"].split(":", 1)
            try:
                saved_layers[name] = verify_local(layer, target["database"], workspace, target["schema"], saved_dir)
            except Exception as exc:
                saved_layers[name] = {"status": "FAIL", "error": str(exc)}
    preserved_layers_pass = all(item.get("status") == "passed" for item in saved_layers.values())
    checked = tests["status"] == "PASS"
    replay_pass = all(row["identical"] for row in fixture_replays) and fixture_replays[0] == fixture_replays[1]
    if zurich["status"] != "NOT_AVAILABLE":
        replay_pass = replay_pass and zurich["status"] == "PASS"
    fixture_complete = fixture["metadata"]["bilingual_complete_count"]
    review_complete = name_review["status"] == "REVIEWED"
    publication = speed["publication_verification"] if speed else {"status": "FAIL" if publication_target else "NOT_AVAILABLE"}
    evaluation_command = "python run.py evaluate --out output/evaluation"
    criteria = {
        "A1": _criterion("PASS" if checked else "FAIL", "Denied sources are never collected; declarations validated",
                         "Official benchmark and operator/legal approval",
                         "python -m unittest tests.test_source_policy tests.test_reports -v",
                         {"suite": tests["status"], "declared_sources": policy["source_count"], "legal_approval": "NOT_CERTIFIED"}),
        "A2": _criterion("PASS" if checked else "FAIL", "Four-process pacing and actual loopback HTTP arrivals; robots, retry/date/backoff, ceiling and 304 tests",
                         "Official deployment/source workload",
                         "python -m unittest tests.test_source_load tests.test_source_policy tests.test_pipeline -v",
                         {"suite": tests["status"], "external_source_requests_in_tests": 0}),
        "A3": _criterion("PASS" if checked and preserved_layers_pass and publication.get("status") != "FAIL" else "FAIL",
                         "Fixture provenance/attribution; optional real publication verification",
                         "Official benchmark attribution audit", benchmark_command if publication_target else evaluation_command,
                         {"fixture_provenance": fixture_gold["field_provenance"], "publication": publication, "preserved_layers": saved_layers}),
        "A4": _criterion("PASS" if fixture_gold["precision"] >= 0.92 else "FAIL",
                         "Project-authored pairwise labels; conflicting-phone and Zurich regressions",
                         "Official labelled Riyadh and held-out AOI", evaluation_command,
                         {"precision": fixture_gold["precision"], "false_merge_pairs": fixture_gold["false_merge_pairs"]}),
        "A5": _criterion("PASS" if fixture_gold["recall"] >= 0.85 else "FAIL", "Project-authored pairwise labels",
                         "Official labelled Riyadh and held-out AOI", evaluation_command,
                         {"recall": fixture_gold["recall"], "missed_merge_pairs": fixture_gold["missed_merge_pairs"]}),
        "A6": _criterion("NOT_CERTIFIED", "244-leaf taxonomy validated; unmapped/ambiguous mappings reported",
                         "Official category gold labels", evaluation_command,
                         {"leaf_count": taxonomy["leaf_count"], "coverage": taxonomy["coverage"],
                          "review_queue_count": taxonomy["review_queue_count"]}),
        "A7": _criterion("PASS" if fixture_complete == fixture["feature_count"] and
                         (zurich["status"] == "NOT_AVAILABLE" or zurich["bilingual_complete"] == zurich["count"]) else "FAIL",
                         "Generated names preserve source values and carry method/version/confidence/provenance",
                         "Official corpus bilingual coverage",
                         "python -m unittest tests.test_enrichment tests.test_name_review -v",
                         {"fixture_complete": fixture_complete, "fixture_count": fixture["feature_count"],
                          "zurich_complete": zurich.get("bilingual_complete"), "zurich_count": zurich.get("count")}),
        "A8": _criterion(("PASS" if name_review["complete_sample_score"] >= 0.90 else "FAIL") if review_complete else "NOT_CERTIFIED",
                         "100 deterministic generated names with explicit human-rating workflow",
                         "Official platform acceptance of recorded review evidence" if review_complete else "Human Arabic review of the 100-name sample",
                         "python run.py review-names --interactive --reviewer YOUR_NAME",
                         name_review),
        "A9": _criterion("NOT_CERTIFIED", "Local source-coordinate preservation is separate from real-world accuracy",
                         "Gold source-of-truth coordinates", benchmark_command if publication_target else evaluation_command,
                         {"publication": publication, "zurich_coordinates_preserved": zurich.get("stable_ids_and_coordinates_preserved")}),
        "A10": _criterion(incremental["status"], "Repeated fixture classifies 50 adds, 50 updates, 20 removals, 30 unchanged",
                          "Official seeded change set", evaluation_command, incremental),
        "A11": _throughput_criterion(speed, benchmark_command),
        "A12": _criterion("PASS" if replay_pass and checked and preserved_layers_pass else "FAIL",
                          "Two exact canonical replays; capture integrity and transformation/conflation sidecars",
                          "Official full provenance replay corpus",
                          "python run.py replay " + str(fixture_dir.relative_to(ROOT) if fixture_dir.is_relative_to(ROOT) else fixture_dir),
                          {"fixture_replay_checks": fixture_replays, "zurich": zurich}),
    }
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "suite": "local_with_publication" if publication_target else "local_offline",
              "unit_tests": tests, "license_report": policy, "taxonomy_report": taxonomy,
              "fixture_conflation": fixture_gold, "fixture_exact_replay": fixture_replays[0],
              "incremental_probe": incremental, "arabic_name_review": name_review,
              "synthetic_throughput": speed or {"status": "FAIL", "output": benchmark.stderr},
              "local_publication": publication, "preserved_layers_verification": saved_layers, "zurich_capture": zurich,
              "live_place_provider": "NOT_AVAILABLE", "live_geocoding_provider": "NOT_AVAILABLE",
              "common_agent_contract": "NOT_AVAILABLE", "official_gold": "NOT_AVAILABLE", "criteria": criteria}
    _write(output_dir / "report.json", report)
    _write(output_dir / "license_report.json", policy)
    _write(output_dir / "taxonomy_report.json", taxonomy)
    if readiness_path:
        lines = ["# Agent 1 submission readiness", "",
                 "Generated from actual local evidence. Every official status remains NOT_CERTIFIED.",
                 "", "| Criterion | Local status | Official status | Evidence | Remaining blocker |",
                 "| --- | --- | --- | --- | --- |"]
        for name, item in criteria.items():
            lines.append("| " + " | ".join([name, item["local_status"], item["official_status"],
                                            item["evidence"], item["remaining_blocker"]]) + " |")
        lines.extend(["", "## Commands and outputs", "",
                      "Each criterion in the machine-readable report includes its command and observed output.",
                      f"Tests: {tests['tests']}; passed: {tests['passed']}; failed: {tests['failed']}; skipped: {tests['skipped']}.",
                      f"Arabic review: {name_review['reviewed']}/{name_review['total']} reviewed; status {name_review['status']}.",
                      "", "## External blockers", "", "- Common Agent Contract and official gold labels are unavailable.",
                      "- Source policy declarations require operator/legal approval.",
                      "- Official benchmark hardware evidence is unavailable.",
                      "- No licensed live place/geocoder provider is configured.", ""])
        if not review_complete:
            lines.extend(['- Human Arabic review is incomplete.', ''])
        readiness_path.parent.mkdir(parents=True, exist_ok=True)
        readiness_path.write_text("\n".join(lines), encoding="utf-8")
    return report
