from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from poi_harvester.enrichment import enrich_record
from poi_harvester.intent import normalize_intent
from poi_harvester.name_review import build_review_dataset, review_names, score_reviews


class NameReviewTests(unittest.TestCase):
    def test_corpus_is_100_deterministic_unreviewed_examples(self):
        dataset = build_review_dataset()
        self.assertEqual(dataset, build_review_dataset())
        self.assertEqual(dataset["count"], 100)
        self.assertEqual(len({entry["id"] for entry in dataset["entries"]}), 100)
        self.assertTrue(all(entry["review_status"] == "NOT_REVIEWED" for entry in dataset["entries"]))
        self.assertEqual(dataset, json.loads((ROOT / "fixtures/arabic_name_review.json").read_text(encoding="utf-8")))
        score = score_reviews(dataset)
        self.assertIsNone(score["human_acceptance_score"])
        self.assertEqual(score["status"], "NOT_REVIEWED")
        self.assertEqual(score["official_status"], "NOT_CERTIFIED")

    def test_ratings_must_have_reviewer_and_match_dataset(self):
        dataset = build_review_dataset()
        with self.assertRaisesRegex(ValueError, "different dataset"):
            score_reviews(dataset, {"dataset_hash": "fake", "ratings": []})
        with TemporaryDirectory() as temp:
            root = Path(temp)
            dataset_path = root / "dataset.json"
            dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
            score = review_names(dataset_path, root / "ratings.json", root / "score.json")
            ratings = json.loads((root / "ratings.json").read_text(encoding="utf-8"))
            ratings["ratings"] = [{"id": dataset["entries"][0]["id"], "rating": "ACCEPT", "reviewer": ""}]
            with self.assertRaisesRegex(ValueError, "human reviewer"):
                score_reviews(dataset, ratings)
            self.assertEqual(score["reviewed"], 0)

    def test_interactive_review_resumes_and_partial_score_is_not_complete(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            dataset_path = root / "dataset.json"
            dataset_path.write_text(json.dumps(build_review_dataset()), encoding="utf-8")
            with patch("builtins.input", side_effect=["a", "r", "q"]), patch("builtins.print"):
                report = review_names(dataset_path, root / "ratings.json", root / "score.json", True, "Test human input")
            self.assertEqual(report["reviewed"], 2)
            self.assertEqual(report["human_acceptance_score"], 0.5)
            self.assertIsNone(report["complete_sample_score"])
            with patch("builtins.input", side_effect=["a", "q"]), patch("builtins.print"):
                resumed = review_names(dataset_path, root / "ratings.json", root / "score.json", True, "Test human input")
            self.assertEqual(resumed["reviewed"], 3)

    def test_mixed_name_numeric_and_location_terms_are_deterministic(self):
        examples = [("Al Nakheel مستشفى", "hospital"), ("Pharmacy 12", "pharmacy"),
                    ("Olaya Street Pharmacy", "pharmacy")]
        for name, category in examples:
            with self.subTest(name=name):
                first, reason = enrich_record({"name_en": name, "category": category}, "test:1")
                second, _ = enrich_record({"name_en": name, "category": category}, "test:1")
                self.assertEqual(first, second)
                self.assertTrue(first["name_ar_generated"])
                self.assertEqual(first["name_en"], name)
                self.assertTrue(first["provenance_name_ar"].startswith("generated:"))
        self.assertEqual(enrich_record({"name_en": "Al Nakheel مستشفى", "category": "hospital"}, "test:1")[0]["name_ar"], "مستشفى النخيل")
        self.assertIn("شارع", enrich_record({"name_en": "Olaya Street Pharmacy", "category": "pharmacy"}, "test:1")[0]["name_ar"])
        english, _ = enrich_record({"name_ar": "صراف آلي النخيل", "category": "amenity_atm"}, "test:2")
        self.assertEqual(english["name_en"], "Al Nakheel ATM")

    def test_cached_low_confidence_generated_values_still_need_review(self):
        generated, reason = enrich_record({"name_en": "Zyrol Pharmacy", "category": "pharmacy"}, "fixture:1")
        self.assertIsNotNone(reason)
        repeated, reason = enrich_record(generated, "fixture:1")
        self.assertEqual(repeated, generated)
        self.assertIsNotNone(reason)

    def test_generic_worship_category_does_not_invent_a_mosque(self):
        generated, _ = enrich_record({"name_en": "Al Nakheel", "category": "amenity_place_of_worship"}, "fixture:1")
        self.assertEqual(generated["name_ar"], "دار عبادة النخيل")

    def test_common_arabic_phrases_use_canonical_categories(self):
        phrases = {"هات الصيدليات": "pharmacy", "عايز المستشفيات": "hospital",
                   "أماكن المطاعم": "amenity_restaurant", "الفنادق الموجودة في المنطقة": "tourism_hotel",
                   "مساجد": "amenity_place_of_worship", "مدارس": "school", "محطات وقود": "amenity_fuel",
                   "بنوك": "amenity_bank", "عيادات": "clinic", "مخابز": "shop_bakery"}
        for phrase, category in phrases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(normalize_intent(phrase)["categories"], (category,))


if __name__ == "__main__":
    unittest.main()
