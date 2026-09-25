from pathlib import Path
from unittest.mock import patch
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from poi_harvester.geocode_http import HttpGeocoder


PROVIDER = {
    "name": "operator_geocoder", "endpoint": "https://example.test/search",
    "license": "operator declared", "attribution": "Operator geocoder",
    "allowed_uses": ["internal"], "commercial_use": False,
    "rate_limit_per_second": 0.5, "reliability_weight": 0.8,
}


class HttpGeocoderTests(unittest.TestCase):
    def test_license_gate_precedes_network(self):
        with patch("poi_harvester.geocode_http._get_json") as getter:
            with self.assertRaises(PermissionError):
                HttpGeocoder(PROVIDER, "commercial", "contact@example.com")
            getter.assert_not_called()

    def test_single_result_is_derived_capped_attributed_and_cached(self):
        response = [{"lat": "24.71", "lon": "46.67", "osm_type": "node", "osm_id": 7}]
        with patch("poi_harvester.geocode_http._source_limiter") as limiter, \
                patch("poi_harvester.geocode_http._robots_allowed", return_value=True), \
                patch("poi_harvester.geocode_http._get_json", return_value=(response, {})) as getter:
            geocoder = HttpGeocoder(PROVIDER, "internal", "contact@example.com")
            first = geocoder.lookup("123 Main Street")
            second = geocoder.lookup("123 Main Street")
        self.assertEqual(first, second)
        self.assertEqual(first["reference"], "node/7")
        self.assertEqual(first["confidence"], 0.5)
        self.assertEqual(first["attribution"], "Operator geocoder")
        self.assertEqual(getter.call_count, 1)
        limiter.return_value.wait.assert_called_once()

    def test_ambiguous_result_goes_to_review(self):
        response = [{"lat": "24.71", "lon": "46.67"},
                    {"lat": "24.72", "lon": "46.68"}]
        with patch("poi_harvester.geocode_http._source_limiter"), \
                patch("poi_harvester.geocode_http._robots_allowed", return_value=True), \
                patch("poi_harvester.geocode_http._get_json", return_value=(response, {})):
            self.assertIsNone(HttpGeocoder(PROVIDER, "internal", "contact@example.com").lookup("Main Street"))

    def test_robots_denial_prevents_geocoding_query(self):
        with patch("poi_harvester.geocode_http._source_limiter"), \
                patch("poi_harvester.geocode_http._robots_allowed", return_value=False), \
                patch("poi_harvester.geocode_http._get_json") as getter:
            with self.assertRaises(PermissionError):
                HttpGeocoder(PROVIDER, "internal", "contact@example.com").lookup("Main Street")
            getter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
