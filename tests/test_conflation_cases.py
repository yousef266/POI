from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from poi_harvester.core import canonicalize, conflate, distance_m


def point(source, identifier, **changes):
    row = {"id": identifier, "lat": 24.71, "lon": 46.67, "category": "pharmacy",
           "name_en": "Al Nakheel Pharmacy", "phone": "+966 11 555 0101", "address": "Olaya Street, Riyadh"}
    row.update(changes)
    return canonicalize(row, {"name": source, "license": "project fixture",
                              "attribution": "Project fixture", "reliability_weight": 0.8})


class ConflationCases(unittest.TestCase):
    def test_exact_multi_source_duplicate_and_field_provenance(self):
        first = point("a", "1")
        second = point("b", "2", hours="09:00-22:00")
        decisions = []
        result = conflate([first, second], decision_log=decisions)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["provenance"]["hours"], "b:2")
        self.assertEqual(decisions[0]["decision"], "MERGE")
        self.assertEqual(decisions[0]["address_similarity"], 1.0)

    def test_arabic_english_and_transliteration_variants_without_phone(self):
        variants = [{"name_en": None, "name_ar": "صيدلية النخيل"},
                    {"name_en": "El Nakhil Pharmacy"}]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertEqual(len(conflate([point("a", "1", phone=None),
                                              point("b", "2", phone=None, **variant)])), 1)

    def test_conflicting_phones_never_merge_across_sources_or_through_bridge(self):
        first, second = point("a", "1"), point("b", "2", phone="999")
        decisions = []
        self.assertEqual(len(conflate([first, second], decision_log=decisions)), 2)
        self.assertEqual(decisions[0]["reason"], "conflicting_phone_numbers")
        self.assertEqual(len(conflate([first, second], algorithm_version=2)), 1)
        bridge = point("c", "3", phone=None)
        self.assertEqual(len(conflate([first, second, bridge])), 2)

    def test_matching_phone_normalization_and_missing_phone(self):
        first = point("a", "1")
        for phone in ("966115550101", None):
            with self.subTest(phone=phone):
                self.assertEqual(len(conflate([first, point("b", "2", phone=phone)])), 1)

    def test_far_apart_and_category_mismatch_never_merge(self):
        first = point("a", "1")
        far = point("b", "2", lat=24.72)
        self.assertGreater(distance_m(first, far), 75)
        self.assertEqual(len(conflate([first, far])), 2)
        decisions = []
        self.assertEqual(len(conflate([first, point("b", "2", category="clinic")], decision_log=decisions)), 2)
        self.assertEqual(decisions[0]["reason"], "category_mismatch")

    def test_address_similarity_is_diagnostic_not_a_override_for_distance_or_phone(self):
        decisions = []
        conflate([point("a", "1"), point("b", "2", address="Olaya St, Riyadh")], decision_log=decisions)
        self.assertGreater(decisions[0]["address_similarity"], 0.8)
        self.assertEqual(len(conflate([point("a", "1"), point("b", "2", lat=25)])), 2)


if __name__ == "__main__":
    unittest.main()
