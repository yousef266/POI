from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from poi_harvester.conflation_eval import evaluate_conflation
from poi_harvester.core import Area, Request
from poi_harvester.pipeline import run
from poi_harvester.reports import license_report, taxonomy_report


class ReportTests(unittest.TestCase):
    def test_license_report_preserves_osm_restriction(self):
        report = license_report(ROOT / "sources.json")
        osm = next(item for item in report["sources"] if item["source"] == "osm_swiss")
        self.assertEqual(osm["allowed_use"], ["internal"])
        self.assertFalse(osm["commercial_use"])
        self.assertFalse(osm["redistribution"])
        self.assertEqual(osm["legal_approval"], "NOT_CERTIFIED")

    def test_taxonomy_coverage_report_and_review_queue(self):
        with TemporaryDirectory() as temp:
            queue = Path(temp) / "review.json"
            queue.write_text(json.dumps([{"reason": "Unmapped category mystery", "record": {}}]),
                             encoding="utf-8")
            report = taxonomy_report(queue)
        self.assertEqual(report["leaf_count"], 244)
        self.assertGreaterEqual(report["coverage"]["osm"]["mapping_count"], 200)
        self.assertEqual(report["source_category_review_count"], 1)
        self.assertEqual(report["official_category_accuracy"], "NOT_CERTIFIED")

    def test_fixture_conflation_and_provenance_scores(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)
            run(Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal"),
                ROOT / "sources.json", out, {"demo", "demo_alt"})
            report = evaluate_conflation(out / "records.json", ROOT / "fixtures/conflation_gold.json")
            self.assertEqual(report["precision"], 1.0)
            self.assertEqual(report["recall"], 1.0)
            self.assertEqual(report["f1"], 1.0)
            self.assertEqual(report["field_provenance"]["accuracy"], 1.0)
            self.assertEqual(report["official_status"], "NOT_CERTIFIED")

    def test_false_and_missed_merges_are_reported(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "records.json").write_text(json.dumps([
                {"source_keys": ["a", "b"], "provenance": {}},
                {"source_keys": ["c"], "provenance": {}},
            ]), encoding="utf-8")
            (root / "gold.json").write_text(json.dumps({"entities": [
                {"source_key": "a", "entity_id": "one"},
                {"source_key": "b", "entity_id": "two"},
                {"source_key": "c", "entity_id": "one"},
            ]}), encoding="utf-8")
            report = evaluate_conflation(root / "records.json", root / "gold.json")
            self.assertEqual(report["false_merge_pairs"], [["a", "b"]])
            self.assertEqual(report["missed_merge_pairs"], [["a", "c"]])
            self.assertEqual(report["f1"], 0.0)


if __name__ == "__main__":
    unittest.main()
