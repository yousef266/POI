from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from poi_harvester.core import Area, Request
from poi_harvester.pipeline import replay, run


class CaptureAuditTests(unittest.TestCase):
    def test_source_capture_original_values_transformations_and_two_replays(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)
            run(Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal"),
                ROOT / "sources.json", out, {"demo", "demo_alt"})
            captures = json.loads((out / "source_capture.json").read_text(encoding="utf-8"))
            original = next(row for cap in captures for row in cap["records"] if row["id"] == "alt-501")
            self.assertNotIn("name_ar", original)
            audit = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
            transformed = next(row for row in audit["transformations"] if row["source_key"] == "demo_alt:alt-501")
            self.assertTrue(transformed["enrichment"]["name_ar"]["generated"])
            self.assertTrue(transformed["capture_hash"])
            self.assertTrue(transformed["retrieval_timestamp"])
            self.assertTrue(audit["conflation_candidate_decisions"])
            one, two = replay(out), replay(out)
            self.assertEqual(one, two)
            self.assertTrue(one["identical"])
            self.assertEqual(one["capture_integrity"]["status"], "PASS")

    def test_changed_capture_is_detected_even_when_final_records_unchanged(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)
            run(Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal"),
                ROOT / "sources.json", out, {"demo"})
            captures = json.loads((out / "source_capture.json").read_text(encoding="utf-8"))
            captures[0]["records"][0]["name_en"] = "Altered"
            (out / "source_capture.json").write_text(json.dumps(captures), encoding="utf-8")
            result = replay(out)
            self.assertFalse(result["identical"])
            self.assertEqual(result["capture_integrity"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
