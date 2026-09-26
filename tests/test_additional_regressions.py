from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from poi_harvester.core import Area, Request
from poi_harvester.enrichment import enrich_record
from poi_harvester.geocode import CatalogGeocoder
from poi_harvester.geocode_http import HttpGeocoder
from poi_harvester.pipeline import replay, reprocess_capture, run
from poi_harvester.place import HttpPlaceResolver
from poi_harvester.validation import incremental_probe


class AdditionalRegressions(unittest.TestCase):
    def test_unknown_category_is_reviewed_without_spending_a_geocoder_request(self):
        record = {"id": "unknown", "category": "unmapped", "address": "Test address"}
        geocoder = Mock()
        with TemporaryDirectory() as temp, patch("poi_harvester.pipeline.collect", return_value=([record], None)):
            out = Path(temp)
            result = run(Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal"),
                         ROOT / "sources.json", out, {"demo"}, geocoder=geocoder)
            self.assertEqual(result["feature_count"], 0)
            queue = json.loads((out / "review_queue.json").read_text(encoding="utf-8"))
            self.assertIn("Unmapped source category", queue[0]["reason"])
            geocoder.lookup.assert_not_called()

    def test_empty_source_selection_cannot_emit_an_empty_replacement_layer(self):
        with TemporaryDirectory() as temp:
            out = Path(temp) / "empty"
            with self.assertRaisesRegex(ValueError, "at least one source"):
                run(Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal"),
                    ROOT / "sources.json", out, set())
            self.assertFalse(out.exists())

    def test_generated_fuel_station_generic_is_translated_both_directions(self):
        arabic, _ = enrich_record({"name_en": "Al Nakheel Fuel Station", "category": "amenity_fuel"}, "fixture:1")
        self.assertEqual(arabic["name_ar"], "محطة وقود النخيل")
        english, _ = enrich_record({"name_ar": "محطة وقود النخيل", "category": "amenity_fuel"}, "fixture:2")
        self.assertEqual(english["name_en"], "Al Nakheel Fuel Station")

    def test_nonpositive_provider_rate_fails_before_network(self):
        provider = {"name": "fixture", "endpoint": "https://example.test/search", "license": "test",
                    "attribution": "test", "allowed_uses": ["internal"], "commercial_use": False,
                    "rate_limit_per_second": -1}
        for adapter in (HttpGeocoder, HttpPlaceResolver):
            with self.subTest(adapter=adapter.__name__):
                with self.assertRaisesRegex(ValueError, "rate"):
                    adapter(provider, "internal", "fixture@example.test")

    def test_incremental_probe_repeats_exact_field_changes(self):
        with TemporaryDirectory() as temp:
            result = incremental_probe(Path(temp))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["counts"], {"added": 50, "updated": 50, "removed": 20, "unchanged": 30})
        self.assertTrue(result["repeated_change_set_identical"])
        self.assertTrue(result["field_phone_diffs_verified"])

    def test_reprocessing_derived_capture_keeps_provider_attribution_without_live_provider(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = {"name": "fixture", "kind": "fixture", "path": "source.json", "license": "test",
                      "attribution": "Test source", "allowed_uses": ["internal"], "commercial_use": False,
                      "auth_mode": "none", "coverage_bbox": None, "freshness": "fixture",
                      "rate_limit_per_second": 1, "reliability_weight": 0.9}
            (root / "registry.json").write_text(json.dumps({"sources": [source]}), encoding="utf-8")
            (root / "source.json").write_text(json.dumps([{"id": "1", "category": "pharmacy",
                                                           "name_en": "Al Nakheel Pharmacy", "address": "Test address"}]), encoding="utf-8")
            catalog = {"provider": {"name": "lookup", "license": "test", "attribution": "Test geocoder",
                                    "allowed_uses": ["internal"], "commercial_use": False},
                       "entries": [{"id": "point-1", "address": "Test address", "lat": 24.71, "lon": 46.67, "confidence": 0.8}]}
            path = root / "catalog.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            geocoder = CatalogGeocoder(path, "internal")
            run(Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal"),
                root / "registry.json", root / "first", {"fixture"}, geocoder=geocoder)
            result = reprocess_capture(root / "first", root / "second")
            self.assertIn("Test geocoder", {item["attribution"] for item in result["metadata"]["contributors"]})
            row = json.loads((root / "second" / "records.json").read_text(encoding="utf-8"))[0]
            self.assertEqual(row["geometry_method"], "geocode_derived")
            self.assertEqual(row["confidence"], 0.5)
            self.assertTrue(replay(root / "second")["identical"])
            catalog["entries"][0]["confidence"] = -1
            path.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "confidence"):
                CatalogGeocoder(path, "internal")


if __name__ == "__main__":
    unittest.main()
