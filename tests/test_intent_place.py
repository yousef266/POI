from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from poi_harvester.agent import invoke
from poi_harvester.intent import normalize_intent
from poi_harvester.place import CatalogPlaceResolver, HttpPlaceResolver, choose_unique_place


class IntentPlaceTests(unittest.TestCase):
    def test_arabic_multi_category_city(self):
        result = normalize_intent("كل الصيدليات والعيادات في الرياض")
        self.assertEqual(result["language"], "ar")
        self.assertEqual(result["categories"], ("clinic", "pharmacy"))
        self.assertEqual(result["area"], "الرياض")
        self.assertEqual(result["unresolved_terms"], [])

    def test_arabic_restaurants_near_and_schools_region(self):
        nearby = normalize_intent("المطاعم القريبة من الحرم")
        self.assertEqual(nearby["categories"], ("amenity_restaurant",))
        self.assertEqual(nearby["area"], "الحرم")
        self.assertEqual(nearby["constraints"]["radius_m"], 500)
        schools = normalize_intent("المدارس في المنطقة الشرقية")
        self.assertEqual(schools["categories"], ("school",))
        self.assertEqual(schools["area"], "المنطقة الشرقية")

    def test_english_near_and_unresolved_terms(self):
        result = normalize_intent("clinics near King Fahd Road")
        self.assertEqual(result["categories"], ("clinic",))
        self.assertEqual(result["area"], "King Fahd Road")
        self.assertTrue(result["constraints"]["near"])
        unresolved = normalize_intent("find something in Riyadh")
        self.assertIn("category", unresolved["unresolved_terms"])

    def test_catalog_place_intent_runs_without_manual_boundary_per_request(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "places.geojson"
            feature = {"type": "Feature", "properties": {"name": "Test District", "id": "district-1"},
                       "geometry": {"type": "Polygon", "coordinates": [[
                           [46.6, 24.6], [46.8, 24.6], [46.8, 24.8],
                           [46.6, 24.8], [46.6, 24.6]]]}}
            path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}),
                            encoding="utf-8")
            result = invoke({"intent": "pharmacies in Test District", "place_catalog": str(path),
                             "sources": ["demo"], "publish": False,
                             "output_dir": str(Path(temp) / "run")})
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["feature_count"], 2)
            self.assertEqual(result["metadata"]["area_resolution"]["source_id"], "district-1")

    def test_catalog_policy_denial_and_ambiguity(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "places.geojson"
            geometry = {"type": "Polygon", "coordinates": [[
                [46.6, 24.6], [46.8, 24.6], [46.8, 24.8], [46.6, 24.8], [46.6, 24.6]]]}
            features = [{"type": "Feature", "properties": {"name": "Twin", "id": str(i)},
                         "geometry": geometry} for i in (1, 2)]
            catalog = {"type": "FeatureCollection", "features": features,
                       "provider": {"name": "restricted", "license": "test",
                                    "attribution": "test", "allowed_uses": ["internal"],
                                    "commercial_use": False}}
            path.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaises(PermissionError):
                CatalogPlaceResolver(path, "commercial")
            resolved = choose_unique_place(CatalogPlaceResolver(path, "internal"), "Twin")
            self.assertEqual(resolved["status"], "needs_input")
            self.assertEqual(len(resolved["candidates"]), 2)

    def test_http_nearby_point_uses_derived_radius_and_ambiguous_results_need_input(self):
        provider = {"name": "operator_search", "endpoint": "https://example.test/search",
                    "license": "operator declared", "attribution": "Operator search",
                    "allowed_uses": ["internal"], "commercial_use": False,
                    "rate_limit_per_second": 1}
        point = [{"display_name": "Test Road", "osm_type": "way", "osm_id": 42,
                  "geojson": {"type": "LineString", "coordinates": [[46.7, 24.7], [46.71, 24.71]]},
                  "lat": "24.7", "lon": "46.7"}]
        with patch("poi_harvester.place._robots_allowed", return_value=True), \
                patch("poi_harvester.place._get_json", return_value=(point, {})), \
                patch("poi_harvester.place._source_limiter"):
            resolved = choose_unique_place(
                HttpPlaceResolver(provider, "internal", "contact@example.com"),
                "Test Road", 500)
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["metadata"]["method"], "derived_nearby_bbox")
        self.assertEqual(resolved["metadata"]["source_id"], "way/42")
        self.assertTrue(resolved["area"].contains(24.7, 46.7))
        self.assertFalse(resolved["area"].contains(24.8, 46.8))
        self.assertTrue(resolved["area"].contains(24.71, 46.71))
        with patch("poi_harvester.place._robots_allowed", return_value=True), \
                patch("poi_harvester.place._get_json", return_value=(point * 2, {})), \
                patch("poi_harvester.place._source_limiter"):
            ambiguous = choose_unique_place(
                HttpPlaceResolver(provider, "internal", "contact@example.com"),
                "Test Road", 500)
        self.assertEqual(ambiguous["status"], "needs_input")
        self.assertEqual(len(ambiguous["candidates"]), 2)

    def test_http_adapter_is_policy_gated_and_provenance_preserving(self):
        provider = {"name": "operator_search", "endpoint": "https://example.test/search",
                    "license": "operator declared", "attribution": "Operator search",
                    "allowed_uses": ["internal"], "commercial_use": False,
                    "rate_limit_per_second": 1}
        with self.assertRaises(PermissionError):
            HttpPlaceResolver(provider, "commercial", "contact@example.com")
        polygon = {"type": "Polygon", "coordinates": [[
            [46.6, 24.6], [46.8, 24.6], [46.8, 24.8], [46.6, 24.8], [46.6, 24.6]]]}
        response = [{"display_name": "Riyadh", "osm_type": "relation", "osm_id": 123,
                     "geojson": polygon}]
        with patch("poi_harvester.place._robots_allowed", return_value=True), \
                patch("poi_harvester.place._get_json", return_value=(response, {})), \
                patch("poi_harvester.place._source_limiter"):
            resolved = choose_unique_place(HttpPlaceResolver(provider, "internal", "contact@example.com"),
                                           "Riyadh")
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["metadata"]["source_id"], "relation/123")
        self.assertEqual(resolved["metadata"]["attribution"], "Operator search")
        self.assertTrue(resolved["area"].contains(24.7, 46.7))


if __name__ == "__main__":
    unittest.main()
