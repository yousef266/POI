from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from poi_harvester.core import canonicalize, conflate
from poi_harvester.enrichment import VERSION, enrich_record


class EnrichmentTests(unittest.TestCase):
    def test_proper_noun_and_generic_term_have_different_treatment(self):
        result, review = enrich_record({"name_en": "Al Nakheel Hospital", "category": "hospital"}, "osm:1")
        self.assertIsNone(review)
        self.assertEqual(result["name_ar"], "مستشفى النخيل")
        self.assertEqual(result["name_en"], "Al Nakheel Hospital")
        self.assertEqual(result["name_ar_version"], VERSION)
        self.assertEqual(result["provenance_name_ar"], f"generated:{VERSION}:osm:1")

    def test_german_generic_pharmacy_word_is_translated(self):
        result, _ = enrich_record({"name_en": "Olympia Apotheke", "category": "pharmacy"}, "osm:2")
        self.assertEqual(result["name_ar"], "صيدلية أوليمبيا")
        self.assertNotIn("أبوثيك", result["name_ar"])

    def test_arabic_to_english(self):
        result, _ = enrich_record({"name_ar": "صيدلية النخيل", "category": "pharmacy"}, "osm:3")
        self.assertEqual(result["name_en"], "Al Nakheel Pharmacy")
        self.assertEqual(result["name_en_method"], "generic_translation+proper_transliteration")

    def test_mixed_arabic_latin(self):
        result, _ = enrich_record({"name_ar": "صيدلية Al Nakheel", "category": "pharmacy"}, "osm:4")
        self.assertEqual(result["name_en"], "Al Nakheel Pharmacy")

    def test_existing_bilingual_values_are_untouched(self):
        source = {"name_en": "Source Name", "name_ar": "اسم المصدر", "category": "pharmacy"}
        result, review = enrich_record(source, "osm:5")
        self.assertEqual(result, source)
        self.assertIsNone(review)

    def test_empty_and_ambiguous_names_are_surfaced(self):
        empty, reason = enrich_record({"name_en": None, "name_ar": None, "category": "pharmacy"}, "osm:6")
        self.assertIsNone(empty.get("name_ar"))
        self.assertIn("no source name", reason)
        ambiguous, reason = enrich_record({"name_en": "Clinic Hospital", "category": "clinic"}, "osm:7")
        self.assertNotIn("name_ar", ambiguous)
        self.assertIn("Conflicting", reason)

    def test_unknown_proper_name_has_lower_confidence(self):
        result, _ = enrich_record({"name_en": "Amavita Pharmacy", "category": "pharmacy"}, "osm:8")
        self.assertEqual(result["name_ar"], "صيدلية أمافيتا")
        unknown, _ = enrich_record({"name_en": "Zyrol Pharmacy", "category": "pharmacy"}, "osm:9")
        self.assertLess(unknown["name_ar_confidence"], result["name_ar_confidence"])

    def test_verified_name_wins_over_generated_in_conflation(self):
        high = {"name": "high", "attribution": "high", "license": "test", "reliability_weight": 0.9}
        low = {"name": "low", "attribution": "low", "license": "test", "reliability_weight": 0.7}
        generated, _ = enrich_record({"id": "1", "lat": 24.71, "lon": 46.67,
                                      "name_en": "Al Nakheel Hospital", "category": "hospital"}, "high:1")
        verified = {"id": "2", "lat": 24.71001, "lon": 46.67001,
                    "name_en": "Al Nakheel Hospital", "name_ar": "مستشفى النخيل المعتمد",
                    "category": "hospital"}
        merged = conflate([canonicalize(generated, high), canonicalize(verified, low)])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["name_ar"], "مستشفى النخيل المعتمد")
        self.assertEqual(merged[0]["provenance"]["name_ar"], "low:2")
        self.assertNotIn("name_ar_method", merged[0])


if __name__ == "__main__":
    unittest.main()
