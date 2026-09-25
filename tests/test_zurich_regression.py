from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from poi_harvester.core import canonicalize, conflate


class ZurichFalseMergeRegression(unittest.TestCase):
    def test_same_named_clinics_with_different_phones_stay_separate(self):
        source = {"name": "synthetic_regression", "attribution": "Project-authored synthetic fixture",
                  "license": "project-authored", "reliability_weight": 0.8}
        rows = json.loads((ROOT / "fixtures/zurich_false_merge.json").read_text(encoding="utf-8"))
        normalized = [canonicalize(row, source) for row in rows]
        self.assertEqual(len(conflate(normalized, algorithm_version=1)), 1)
        corrected = conflate(normalized, algorithm_version=2)
        self.assertEqual(len(corrected), 2)
        self.assertEqual({row["source_keys"][0] for row in corrected},
                         {"synthetic_regression:clinic-1", "synthetic_regression:clinic-2"})


if __name__ == "__main__":
    unittest.main()
