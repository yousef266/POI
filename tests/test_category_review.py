from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from poi_harvester.core import Area, Request
from poi_harvester.pipeline import run
from poi_harvester.reports import taxonomy_report


class CategoryReviewTests(unittest.TestCase):
    def test_unmapped_source_category_is_visible_in_review_report(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "records.json").write_text(json.dumps([{
                "id": "unknown-1", "lat": 24.71, "lon": 46.67,
                "name_en": "Mystery", "category": "unmapped_custom_type",
            }]), encoding="utf-8")
            source = {"name": "fixture", "kind": "fixture", "path": "records.json",
                      "license": "project fixture", "attribution": "Project fixture",
                      "allowed_uses": ["internal"], "commercial_use": False,
                      "auth_mode": "none", "coverage_bbox": None, "freshness": "static",
                      "rate_limit_per_second": 1, "reliability_weight": 0.8}
            (root / "registry.json").write_text(json.dumps({"sources": [source]}), encoding="utf-8")
            out = root / "run"
            result = run(Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal"),
                         root / "registry.json", out, {"fixture"})
            self.assertEqual(result["feature_count"], 0)
            review = json.loads((out / "review_queue.json").read_text(encoding="utf-8"))
            self.assertEqual(len(review), 1)
            self.assertIn("Unmapped source category", review[0]["reason"])
            self.assertEqual(taxonomy_report(out / "review_queue.json")["source_category_review_count"], 1)


if __name__ == "__main__":
    unittest.main()
