"""Validate the explicitly supplied human decisions without changing examples."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from poi_harvester.name_review import build_review_dataset, _dataset_hash, score_reviews, write_review_queue
from poi_harvester.enrichment import VERSION
from poi_harvester.cli import main


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


class HumanReviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.dataset = read(ROOT / 'fixtures/arabic_name_review.json')
        self.ratings = read(ROOT / 'fixtures/arabic_name_review_human_ratings.json')
        self.manifest = read(ROOT / 'fixtures/arabic_name_review_manifest.json')

    def test_human_decisions_cover_exact_existing_ids(self):
        ids = [x['id'] for x in self.dataset['entries']]
        decisions = [x['id'] for x in self.ratings['ratings']]
        self.assertEqual(ids, decisions)
        self.assertEqual(len(decisions), len(set(decisions)))
        score = score_reviews(self.dataset, self.ratings)
        self.assertEqual(100, score['reviewed'])
        self.assertEqual(100, score['accepted'])
        self.assertEqual(0, score['rejected'])
        self.assertEqual(0, score['unreviewed'])
        self.assertEqual(1.0, score['complete_sample_score'])
        self.assertEqual('NOT_CERTIFIED', score['official_status'])

    def test_input_names_ids_and_transformations_unchanged(self):
        self.assertEqual(build_review_dataset(), self.dataset)
        self.assertEqual(_dataset_hash(self.dataset), self.ratings['dataset_hash'])
        self.assertEqual('EXPLICIT_HUMAN_ATTESTATION_IN_USER_MESSAGE', self.ratings['evidence_type'])
        self.assertTrue(all(x['reviewer'] == 'Yousef' and x['rating'] == 'ACCEPT' for x in self.ratings['ratings']))

    def test_manifest_hashes_bind_input_and_decisions(self):
        self.assertEqual(self.ratings['dataset_hash'], self.manifest['dataset_hash'])
        for field, path in [('dataset_canonical_sha256', 'fixtures/arabic_name_review.json'),
                            ('ratings_canonical_sha256', 'fixtures/arabic_name_review_human_ratings.json')]:
            self.assertEqual(_dataset_hash(read(ROOT / path)), self.manifest[field])
            formatted = json.dumps(read(ROOT / path), indent=4).replace('\n', '\r\n')
            self.assertEqual(_dataset_hash(json.loads(formatted)), self.manifest[field])
        self.assertEqual([x['id'] for x in self.dataset['entries']], self.manifest['all_example_ids'])
        self.assertEqual(set(self.manifest['prior_priority_queue_ids']),
                         {x['id'] for x in self.dataset['entries'] if x['review_reason']})

    def test_completed_priority_queue_preserves_corpus_denominator(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'queue.json'
            queue = write_review_queue(self.dataset, path, self.ratings)
            self.assertEqual(30, len(queue['entries']))
            self.assertEqual(100, queue['human_reviewed'])
            self.assertEqual(0, queue['unreviewed'])
            self.assertTrue(all(x['review_status'] == 'REVIEWED' and x['rating'] == 'ACCEPT' for x in queue['entries']))
            self.assertNotIn('Human decision: pending', path.with_suffix('.md').read_text(encoding='utf-8'))
            self.assertEqual(queue, write_review_queue(self.dataset, path, self.ratings))

    def test_invalid_ratings_rejected_before_queue_write(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'queue.json'
            with self.assertRaisesRegex(ValueError, 'different dataset'):
                write_review_queue(self.dataset, path, {**self.ratings, 'dataset_hash': 'invalid'})
            self.assertFalse(path.exists())

    def test_cli_export_honors_supplied_human_evidence_without_prompts(self):
        with TemporaryDirectory() as tmp, patch('builtins.input', side_effect=AssertionError('No new review requested')), patch('builtins.print'):
            p = Path(tmp)
            code = main(['review-names', '--dataset', str(ROOT / 'fixtures/arabic_name_review.json'),
                         '--ratings', str(ROOT / 'fixtures/arabic_name_review_human_ratings.json'),
                         '--queue-out', str(p / 'queue.json'), '--out', str(p / 'score.json')])
            self.assertEqual(0, code)
            self.assertEqual(100, read(p / 'score.json')['accepted'])
            self.assertEqual(100, read(p / 'queue.json')['human_reviewed'])

    def test_agent_manifest_matches_enrichment_and_review_evidence(self):
        agent = read(ROOT / 'agent.json')
        self.assertEqual(VERSION, agent['enrichment_version'])
        self.assertEqual(self.manifest['human_reviewed'], agent['human_review_evidence']['human_reviewed'])
        self.assertEqual(self.manifest['ratings'], agent['human_review_evidence']['ratings'])
