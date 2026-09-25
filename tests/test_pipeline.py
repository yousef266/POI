from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from poi_harvester.core import Area, Request, area_from_place_catalog, canonicalize, categories_from_text, change_set, conflate, polygon_from_geojson, reconcile_ids
from poi_harvester.pipeline import replay, run
from poi_harvester.agent import invoke
from poi_harvester.geocode import CatalogGeocoder
from poi_harvester.publish import _store, publish
from poi_harvester.sources import TokenBucket, _get_json, _overpass, _robots_allowed, _source_limiter, covers_area, license_gate
from poi_harvester.taxonomy import catalog, google_crosswalk, osm_crosswalk, wikidata_crosswalk


ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def test_named_admin_boundary_catalog(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "places.geojson"
            feature = {"type": "Feature", "properties": {"name": "Test District", "aliases": ["حي تجريبي"]},
                       "geometry": {"type": "Polygon", "coordinates": [[
                           [46.6, 24.6], [46.8, 24.6], [46.8, 24.8],
                           [46.6, 24.8], [46.6, 24.6]]]}}
            path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
            self.assertTrue(area_from_place_catalog(path, "حي تجريبي").contains(24.7, 46.7))
            result = invoke({"place": "Test District", "place_catalog": str(path),
                             "category": "pharmacy", "sources": ["demo"],
                             "publish": False, "output_dir": str(Path(temp) / "named-run")})
            self.assertEqual(result["feature_count"], 2)
            with self.assertRaisesRegex(ValueError, "0 matches"):
                area_from_place_catalog(path, "Missing Place")

    def test_pluggable_geocode_fallback_is_derived_and_attributed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source.json").write_text(json.dumps([{
                "id": "one", "address": "123 Main Street", "category": "pharmacy",
                "name_en": "Main Pharmacy",
            }]), encoding="utf-8")
            source = {"name": "address_source", "kind": "fixture", "path": "source.json",
                      "license": "test", "allowed_uses": ["internal"],
                      "commercial_use": False, "auth_mode": "none", "coverage_bbox": None,
                      "freshness": "test", "attribution": "Address source",
                      "rate_limit_per_second": 1, "reliability_weight": 0.9}
            (root / "registry.json").write_text(json.dumps({"sources": [source]}), encoding="utf-8")
            catalog = {"provider": {"name": "local_lookup", "license": "test",
                                    "attribution": "Local geocode catalog",
                                    "allowed_uses": ["internal"], "commercial_use": False},
                       "entries": [{"id": "a1", "address": "123 Main Street",
                                    "lat": 24.71, "lon": 46.67, "confidence": 0.8}]}
            (root / "geocoder.json").write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaises(PermissionError):
                CatalogGeocoder(root / "geocoder.json", "commercial")
            geocoder = CatalogGeocoder(root / "geocoder.json", "internal")
            out = root / "out"
            run(Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal"),
                root / "registry.json", out, {"address_source"}, geocoder=geocoder)
            records = json.loads((out / "records.json").read_text(encoding="utf-8"))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["geometry_method"], "geocode_derived")
            self.assertEqual(records[0]["geometry_provenance"], "local_lookup:a1")
            self.assertEqual(records[0]["confidence"], 0.5)
            self.assertIn("Local geocode catalog", records[0]["attributions"])
            self.assertTrue(replay(out)["identical"])

    def test_regional_coverage_requires_entire_aoi(self):
        swiss = {"coverage_bbox": [5.9, 45.8, 10.6, 47.9]}
        self.assertTrue(covers_area(swiss, Area(47.37, 8.52, 47.39, 8.55)))
        self.assertFalse(covers_area(swiss, Area(47.37, 8.52, 48.01, 8.55)))
        self.assertFalse(covers_area(swiss, Area(24.7, 46.6, 24.8, 46.8)))

    def test_robots_disallow_prevents_live_query(self):
        request = Request(Area(47.37, 8.52, 47.39, 8.55), "pharmacy", "internal", "test@example.com")
        source = {"endpoint": "https://example.test/api/interpreter", "rate_limit_per_second": 1}
        with patch("poi_harvester.sources._robots_allowed", return_value=False), \
                patch("poi_harvester.sources._get_json") as getter:
            with self.assertRaises(PermissionError):
                _overpass(source, request)
            getter.assert_not_called()

    def test_robots_parser_disallows_endpoint(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self, *_args):
                return b"User-agent: *\nDisallow: /api/\n"
        with patch("poi_harvester.sources.urlopen", return_value=Response()):
            self.assertFalse(_robots_allowed("https://example.test/api/interpreter", "POIHarvesterAgent/0.1 (test@example.com)"))

    def test_token_bucket_waits_between_requests(self):
        times = iter([0.0, 0.0, 0.1, 1.0])
        with patch("poi_harvester.sources.monotonic", side_effect=lambda: next(times)), \
                patch("poi_harvester.sources.sleep") as sleeper:
            bucket = TokenBucket(1)
            bucket.wait()
            bucket.wait()
        sleeper.assert_called_once_with(0.9)

    def test_politeness_ceiling_cannot_raise_declared_source_rate(self):
        source = {"endpoint": "https://unique-rate.test/api", "rate_limit_per_second": 0.2}
        with patch("poi_harvester.sources._LIMITERS", {}):
            self.assertEqual(_source_limiter(source, 10).rate, 0.2)
            self.assertEqual(_source_limiter(source, 0.1).rate, 0.1)
            self.assertEqual(_source_limiter(source, 10).rate, 0.1)

    def test_50_add_50_update_20_remove_incremental_run(self):
        def poi(index, phone="100"):
            return {"id": str(index), "lat": 10 + index * 0.01, "lon": 20.0,
                    "category": "pharmacy", "name_en": f"Pharmacy {index}", "phone": phone}
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source_file = root / "source.json"
            registry_file = root / "registry.json"
            source = {"name": "seed", "kind": "fixture", "path": "source.json",
                      "license": "project authored", "allowed_uses": ["internal"],
                      "commercial_use": False, "auth_mode": "none", "coverage_bbox": None,
                      "freshness": "test", "attribution": "Seed fixture",
                      "rate_limit_per_second": 1, "reliability_weight": 0.9}
            registry_file.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
            source_file.write_text(json.dumps([poi(i) for i in range(100)]), encoding="utf-8")
            request = Request(Area(9.9, 19.9, 12.0, 20.1), "pharmacy", "internal")
            first = root / "first"
            second = root / "second"
            run(request, registry_file, first, {"seed"})
            source_file.write_text(json.dumps([poi(i, "200" if i < 50 else "100")
                                               for i in range(80)] +
                                              [poi(i) for i in range(100, 150)]), encoding="utf-8")
            run(request, registry_file, second, {"seed"}, first / "records.json")
            changes = json.loads((second / "changes.json").read_text(encoding="utf-8"))
            self.assertEqual(tuple(len(changes[key]) for key in ("added", "updated", "removed", "unchanged")),
                             (50, 50, 20, 30))
            self.assertTrue(all("phone" in row["changed_fields"] for row in changes["updated"]))
            self.assertTrue(replay(second)["identical"])

    def test_taxonomy_crosswalks_and_bilingual_multi_intent(self):
        self.assertGreaterEqual(catalog()["leaf_count"], 200)
        self.assertEqual(osm_crosswalk()["amenity=pharmacy"], "pharmacy")
        self.assertEqual(osm_crosswalk()["shop=bakery"], "shop_bakery")
        self.assertEqual(google_crosswalk()["pharmacy"], "pharmacy")
        self.assertEqual(wikidata_crosswalk()["Q13107184"], "pharmacy")
        self.assertEqual(categories_from_text("bakeries and pharmacies in Zurich"),
                         ("pharmacy", "shop_bakery"))
        self.assertEqual(categories_from_text("صيدليات وعيادات في الرياض"),
                         ("clinic", "pharmacy"))

    def test_multi_category_intent_queries_and_keeps_both_categories(self):
        categories = categories_from_text("all pharmacies and clinics in Zurich")
        self.assertEqual(set(categories), {"pharmacy", "clinic"})
        request = Request(Area(47.37, 8.52, 47.39, 8.55), categories, "internal", "test@example.com")
        source = {"endpoint": "https://example.test/api/interpreter", "rate_limit_per_second": 1}
        response = {"elements": [
            {"type": "node", "id": 1, "lat": 47.38, "lon": 8.53,
             "tags": {"amenity": "pharmacy", "name": "A Pharmacy"}},
            {"type": "node", "id": 2, "lat": 47.381, "lon": 8.531,
             "tags": {"amenity": "clinic", "name": "B Clinic"}},
        ]}
        with patch("poi_harvester.sources._robots_allowed", return_value=True), \
                patch("poi_harvester.sources._get_json", return_value=(response, {"url": "test"})) as getter:
            records, _ = _overpass(source, request)
        self.assertEqual({record["category"] for record in records}, {"pharmacy", "clinic"})
        self.assertIn("pharmacy", getter.call_args.args[0])
        self.assertIn("clinic", getter.call_args.args[0])

    def test_osm_way_center_is_not_published_as_verified_point(self):
        request = Request(Area(47.37, 8.52, 47.39, 8.55), "pharmacy", "internal", "test@example.com")
        source = {"endpoint": "https://example.test/api/interpreter", "rate_limit_per_second": 1}
        response = {"elements": [{"type": "way", "id": 9,
                                  "center": {"lat": 47.38, "lon": 8.53},
                                  "tags": {"amenity": "pharmacy", "name": "Example",
                                           "addr:street": "Main Street", "addr:city": "Zurich"}}]}
        with patch("poi_harvester.sources._robots_allowed", return_value=True), \
                patch("poi_harvester.sources._get_json", return_value=(response, {"url": "test"})):
            records, _ = _overpass(source, request)
        self.assertEqual(len(records), 1)
        self.assertNotIn("lat", records[0])
        self.assertNotIn("lon", records[0])
        self.assertEqual(records[0]["address"], "Main Street, Zurich")
        self.assertIn("way/9", records[0]["footprint_ref"])

    def test_conditional_response_reuses_previous_source_snapshot(self):
        url = "https://example.test/api/interpreter?data=one"
        cache = {"url": url, "etag": '"rev-2"', "last_modified": "Wed, 01 Jan 2025 00:00:00 GMT"}
        requests = []

        def not_modified(request, timeout):
            requests.append(request)
            raise HTTPError(url, 304, "Not Modified", {}, None)

        with patch("poi_harvester.sources.urlopen", side_effect=not_modified):
            payload, returned_cache = _get_json(url, TokenBucket(100), "POIHarvesterAgent/0.1 (test@example.com)", cache)
        self.assertIsNone(payload)
        self.assertEqual(returned_cache, cache)
        self.assertEqual(requests[0].get_header("If-none-match"), '"rev-2"')
        self.assertEqual(requests[0].get_header("If-modified-since"), cache["last_modified"])

    def test_partial_source_failure_cannot_emit_deletions(self):
        def partial(source, *_args):
            if source["name"] == "demo":
                return [{"id": "one", "lat": 24.71, "lon": 46.67,
                         "category": "pharmacy", "name_en": "One Pharmacy"}], None
            raise TimeoutError("source offline")

        with TemporaryDirectory() as temp, patch("poi_harvester.pipeline.collect", side_effect=partial):
            out = Path(temp)
            with self.assertRaisesRegex(RuntimeError, "Harvest incomplete"):
                run(Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal"),
                    ROOT / "sources.json", out, {"demo", "demo_alt"})
            self.assertFalse((out / "changes.json").exists())

    def test_publication_target_is_supplied_per_invocation(self):
        payload = {"bbox": [24.70, 46.66, 24.73, 46.69], "category": "pharmacy"}
        result = invoke(payload)
        self.assertEqual(result["status"], "needs_input")
        self.assertIn("database", result["question"])
        self.assertIn("workspace", result["question"])
        self.assertNotEqual(_store("city_a", "public"), _store("city_b", "public"))
        self.assertNotEqual(_store("city_a", "public"), _store("city_a", "custom"))

    def test_invented_fixture_coordinates_cannot_publish_implicitly(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)
            run(Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal"), ROOT / "sources.json", out, {"demo"})
            with self.assertRaisesRegex(ValueError, "invented"):
                publish(out, "poi_pharmacy", "poi_agent_test", "poi_agent_test")

    def test_demo_run_deduplicates_and_replays_exactly(self):
        with TemporaryDirectory() as temp:
            out = Path(temp) / "run"
            request = Request(Area(24.70, 46.66, 24.73, 46.69), "pharmacy", "internal")
            result = run(request, ROOT / "sources.json", out, {"demo", "demo_alt"})
            self.assertEqual(result["feature_count"], 2)
            self.assertTrue(replay(out)["identical"])
            layer = json.loads((out / "poi.geojson").read_text(encoding="utf-8"))
            self.assertEqual(len(layer["features"]), 2)
            merged = next(feature for feature in layer["features"] if len(feature["properties"]["source_keys"]) == 3)
            self.assertEqual(merged["properties"]["name_ar"], "صيدلية النخيل")
            self.assertEqual(merged["properties"]["provenance_name_ar"], "demo:demo-101")
            self.assertEqual(merged["properties"]["hours"], "09:00-22:00")
            self.assertEqual(merged["properties"]["provenance_hours"], "demo_alt:alt-501")
            self.assertEqual(len(merged["properties"]["attributions"]), 2)

    def test_license_gate_excludes_before_collection(self):
        source = {"name": "restricted", "license": "internal only", "allowed_uses": ["internal"]}
        allowed, reason = license_gate(source, "redistribute")
        self.assertFalse(allowed)
        self.assertIn("not approved", reason)

    def test_change_set_has_field_level_diff(self):
        old = [{"stable_id": "a", "phone": "111"}, {"stable_id": "b", "phone": "222"}]
        new = [{"stable_id": "a", "phone": "333"}, {"stable_id": "c", "phone": "444"}]
        changes = change_set(old, new)
        self.assertEqual(changes["added"], ["c"])
        self.assertEqual(changes["removed"], ["b"])
        self.assertEqual(changes["updated"], [{"stable_id": "a", "changed_fields": ["phone"]}])

    def test_nearby_distinct_phones_and_names_remain_separate(self):
        source = {"name": "demo", "attribution": "fixture", "license": "demo", "reliability_weight": 0.9}
        a = canonicalize({"id": "a", "lat": 24.71, "lon": 46.67, "category": "pharmacy", "name_en": "Central Pharmacy", "phone": "123"}, source)
        b = canonicalize({"id": "b", "lat": 24.71001, "lon": 46.67001, "category": "pharmacy", "name_en": "Sunrise Pharmacy", "phone": "456"}, source)
        self.assertEqual(len(conflate([a, b])), 2)

    def test_nearby_same_source_branches_do_not_conflate(self):
        source = {"name": "osm", "attribution": "OSM", "license": "test", "reliability_weight": 0.8}
        a = canonicalize({"id": "node/1", "lat": 47.38, "lon": 8.53,
                          "category": "pharmacy", "name_en": "Central Pharmacy"}, source)
        b = canonicalize({"id": "node/2", "lat": 47.38002, "lon": 8.53002,
                          "category": "pharmacy", "name_en": "Central Pharmacy"}, source)
        self.assertEqual(len(conflate([a, b])), 2)
        a["phone"] = "+41 44 415 76 06"
        b["phone"] = "+41 44 415 76 10"
        self.assertEqual(len(conflate([a, b])), 2)

    def test_arabic_and_english_names_can_match_without_phone(self):
        first_source = {"name": "en", "attribution": "English", "license": "demo", "reliability_weight": 0.8}
        second_source = {"name": "ar", "attribution": "Arabic", "license": "demo", "reliability_weight": 0.8}
        english = canonicalize({"id": "1", "lat": 24.71, "lon": 46.67, "category": "pharmacy", "name_en": "Al Nakheel Pharmacy"}, first_source)
        arabic = canonicalize({"id": "2", "lat": 24.71001, "lon": 46.67001, "category": "pharmacy", "name_ar": "صيدلية النخيل"}, second_source)
        self.assertEqual(len(conflate([english, arabic])), 1)

    def test_existing_poi_keeps_id_when_new_source_is_added(self):
        old = [{"stable_id": "original", "source_keys": ["one:1"], "name_en": "Al Nakheel"}]
        current = [{"stable_id": "new-hash", "source_keys": ["one:1", "two:99"], "name_en": "Al Nakheel"}]
        reconciled = reconcile_ids(old, current)
        self.assertEqual(reconciled[0]["stable_id"], "original")
        self.assertEqual(change_set(old, reconciled)["added"], [])
        self.assertEqual(change_set(old, reconciled)["removed"], [])

    def test_polygon_aoi_excludes_nearby_outside_poi(self):
        polygon = polygon_from_geojson(json.loads((ROOT / "fixtures/riyadh_small_aoi.geojson").read_text(encoding="utf-8")))
        self.assertTrue(polygon.contains(24.71361, 46.67530))
        self.assertFalse(polygon.contains(24.71430, 46.67620))
        with TemporaryDirectory() as temp:
            result = run(Request(polygon, "pharmacy", "internal"), ROOT / "sources.json", Path(temp), {"demo", "demo_alt"})
            self.assertEqual(result["feature_count"], 1)

    def test_polygon_hole_and_multipolygon_aoi(self):
        outer = [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]
        hole = [[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]]
        second = [[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]]
        area = polygon_from_geojson({"type": "MultiPolygon", "coordinates": [[outer, hole], [second]]})
        self.assertTrue(area.contains(0.5, 0.5))
        self.assertFalse(area.contains(1.5, 1.5))
        self.assertTrue(area.contains(5.5, 5.5))
        self.assertFalse(area.contains(4.5, 4.5))


if __name__ == "__main__":
    unittest.main()
