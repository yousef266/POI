"""Offline authored regressions; no official benchmark or external calls."""
from contextlib import redirect_stderr
from datetime import datetime, timezone, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from poi_harvester.robots import allowed
from poi_harvester.names import bilingual_counts, resolve_osm_names, valid_language_name
from poi_harvester.name_review import build_review_dataset, write_review_queue, review_names
from poi_harvester.snapshots import freshness_state, describe, load_pinned
from poi_harvester.agent import invoke
from poi_harvester.pipeline import run
from poi_harvester.core import Area, Request
from poi_harvester.cli import main
from poi_harvester.sources import _robots_allowed, _overpass, parse_overpass_payload


class EvidenceIntegrityTests(unittest.TestCase):
    def test_provider_wildcard_and_unrooted_exclusions(self):
        rules = ['User-agent: *', 'Disallow: *.osm.pbf', 'Disallow: state.txt', 'Disallow: *updates*']
        for path in ('/africa/egypt-latest.osm.pbf', '/africa/egypt-updates/state.txt', '/state.txt'):
            self.assertFalse(allowed(rules, 'POI-Harvester/1.0', 'https://provider.test' + path))
        self.assertTrue(allowed(rules, 'POI-Harvester/1.0', 'https://provider.test/africa/egypt.html'))

    def test_wildcard_denial_stops_adapter_before_data_request(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, *args): return b'User-agent: *\nDisallow: /*.pbf$'
        with patch('poi_harvester.sources.urlopen', return_value=Response()) as fetch:
            self.assertFalse(_robots_allowed('https://provider.test/latest.pbf', 'POI-Harvester/1.0'))
            self.assertEqual(1, fetch.call_count)
            self.assertEqual('https://provider.test/robots.txt', fetch.call_args.args[0].full_url)

    def test_longest_match_wins_independent_of_rule_order(self):
        for rules in (['Disallow: /', 'Allow: /public'], ['Allow: /public', 'Disallow: /']):
            self.assertTrue(allowed(['User-agent: *'] + rules, 'POI-Harvester', 'https://example.test/public/data'))
            self.assertFalse(allowed(['User-agent: *'] + rules, 'POI-Harvester', 'https://example.test/private'))

    def test_equal_match_prefers_allow(self):
        self.assertTrue(allowed(['User-agent: *', 'Disallow: /same', 'Allow: /same'], 'POI-Harvester', 'https://example.test/same'))

    def test_anchor_and_query_string(self):
        rules = ['User-agent: *', 'Disallow: /*.json$']
        self.assertFalse(allowed(rules, 'Bot', 'https://example.test/data.json'))
        self.assertTrue(allowed(rules, 'Bot', 'https://example.test/data.json?x=1'))

    def test_matching_agent_groups_combined_default_ignored(self):
        rules = ['User-agent: *', 'Disallow: /', 'User-agent: POI-Harvester', 'Disallow: /a',
                 'User-agent: POI-Harvester', 'Disallow: /b']
        for path in ('/a', '/b'):
            self.assertFalse(allowed(rules, 'POI-Harvester/1.0', 'https://example.test' + path))
        self.assertTrue(allowed(rules, 'POI-Harvester/1.0', 'https://example.test/c'))

    def test_unicode_and_percent_encoded_paths(self):
        self.assertFalse(allowed(['User-agent: *', 'Disallow: /صيدلية'], 'Bot', 'https://example.test/%D8%B5%D9%8A%D8%AF%D9%84%D9%8A%D8%A9'))
        self.assertFalse(allowed(['User-agent: *', 'Disallow: /%41'], 'Bot', 'https://example.test/A'))

    def test_empty_rules_and_comments(self):
        self.assertTrue(allowed(['User-agent: *', 'Disallow:', 'Allow: / # comment'], 'Bot', 'https://example.test/a'))

    def row(self, **changes):
        return {'name_en': 'Source Pharmacy', 'name_ar': 'صيدلية المصدر', 'source_keys': ['osm:node/1'],
                'provenance': {'name_en': 'osm:node/1', 'name_ar': 'osm:node/1:tags.alt_name:ar'}, **changes}

    def test_source_names_count_with_selected_field_provenance(self):
        result = bilingual_counts([self.row()])
        self.assertEqual(1, result['authoritative_bilingual'])
        self.assertEqual(1, result['authoritative_bilingual_fraction'])

    def test_generated_translation_not_authoritative(self):
        result = bilingual_counts([self.row(name_ar_method='rules', name_ar_generated=True)])
        self.assertEqual(1, result['valid_bilingual_including_generated'])
        self.assertEqual(0, result['authoritative_bilingual'])

    def test_generated_provenance_not_authoritative_without_method(self):
        self.assertEqual(0, bilingual_counts([self.row(provenance={'name_en': 'osm:node/1', 'name_ar': 'generated:rules:osm:node/1'})])['authoritative_bilingual'])

    def test_missing_provenance_not_authoritative(self):
        self.assertEqual(0, bilingual_counts([self.row(provenance={})])['authoritative_bilingual'])

    def test_invalid_values_not_bilingual_denominator_preserved(self):
        values = [None, '', ' \t ', '\u200b', '123 !!!', '؟؟؟', '\ufffdصيدلية', '\ud800صيدلية', 'صيد\x00لية', 'Latin only']
        result = bilingual_counts([self.row(name_ar=v) for v in values])
        self.assertEqual(len(values), result['total'])
        self.assertEqual(0, result['valid_bilingual_including_generated'])
        self.assertEqual(0, result['authoritative_bilingual_fraction'])

    def test_unicode_script_validity_not_human_approval(self):
        self.assertTrue(valid_language_name(' صَيدلية الـمصدر\u200f ', 'ar'))
        self.assertTrue(valid_language_name('Ｃａｉｒｏ Pharmacy', 'en'))
        self.assertFalse(valid_language_name('اسم عربي', 'en'))

    def test_invalid_primary_name_uses_authoritative_alternate(self):
        row = resolve_osm_names({'name:ar': '???', 'alt_name:ar': 'صيدلية المصدر', 'name:en': 'Source Pharmacy'}, 'osm:1')
        self.assertEqual('صيدلية المصدر', row['name_ar'])
        self.assertEqual('osm:1:tags.alt_name:ar', row['provenance_name_ar'])

    def test_punctuation_does_not_become_an_arabic_name(self):
        row = resolve_osm_names({'name': '؟؟؟', 'name:ar': '123', 'name:en': '\ufffdName'}, 'osm:1')
        self.assertEqual('unnamed_source', row['name_status'])
        self.assertIsNone(row['name_ar'])

    def test_empty_dataset_has_no_success_percentage(self):
        self.assertIsNone(bilingual_counts([])['authoritative_bilingual_fraction'])

    def test_freshness_states_at_use_time(self):
        now = datetime(2026, 9, 27, tzinfo=timezone.utc)
        source = {'max_snapshot_age_seconds': 86400}
        descriptor = {'mode': 'live', 'timestamp': now.isoformat()}
        self.assertEqual('CURRENT', freshness_state(source, descriptor, now))
        self.assertEqual('STALE', freshness_state(source, descriptor, now + timedelta(days=2)))
        self.assertEqual('HISTORICAL', freshness_state(source, {**descriptor, 'mode': 'pinned_capture_not_live'}, now))
        self.assertEqual('UNKNOWN', freshness_state({}, descriptor, now))
        self.assertEqual('UNKNOWN', freshness_state(source, {**descriptor, 'timestamp': 'bad'}, now))

    def test_snapshot_descriptor_has_explicit_historical_state(self):
        source = {'name': 'osm', 'endpoint': 'https://example.test'}
        result = describe(source, Request(Area(29, 31, 30, 32), 'pharmacy', 'internal'),
                          {'osm3s': {'timestamp_osm_base': '2026-07-24T11:04:51Z'}, 'elements': []}, 'pinned_capture_not_live')
        self.assertEqual('HISTORICAL', result['freshness_state'])

    def test_pinning_retains_original_retrieval_timestamp(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            source = {'name': 'osm', 'endpoint': 'https://example.test', 'kind': 'overpass',
                      'auth_mode': 'none', 'license': 'Authored', 'allowed_uses': ['internal'],
                      'commercial_use': False, 'attribution': 'Authored fixture', 'coverage_bbox': None,
                      'freshness': 'authored', 'rate_limit_per_second': 1, 'reliability_weight': .8}
            request = Request(Area(29, 31, 30, 32), 'pharmacy', 'internal')
            element = {'type': 'node', 'id': 1, 'lat': 29.5, 'lon': 31.5, 'tags': {'amenity': 'pharmacy'}}
            (p/'registry.json').write_text(json.dumps({'sources': [source]}), encoding='utf-8')
            record = {'id': 'node/1', 'lat': 29.5, 'lon': 31.5, 'category': 'pharmacy',
                      'source_payload': element, 'source_version': '2026-07-24T11:04:51Z'}
            run(request, p/'registry.json', p/'original', {'osm'}, source_records_override={'osm': [record]})
            capture = json.loads((p/'original/source_capture.json').read_text())
            records, descriptors = load_pinned(p/'original', [source], request, {'osm'})
            original = capture[0]['retrieval_timestamp']
            self.assertEqual(original, descriptors['osm']['original_retrieval_timestamp'])
            run(request, p/'registry.json', p/'pinned', {'osm'}, source_records_override=records, source_snapshots_override=descriptors)
            pinned = json.loads((p/'pinned/source_capture.json').read_text())
            self.assertEqual(original, pinned[0]['retrieval_timestamp'])
            self.assertIn('input_access_timestamp', pinned[0])

    def test_api_refresh_failure_is_explicit(self):
        with patch('poi_harvester.agent.run', side_effect=TimeoutError('no fallback')):
            result = invoke({'bbox': [29, 31, 30, 32], 'category': 'pharmacy', 'publish': False})
        self.assertEqual('failed', result['status'])
        self.assertEqual('FAILED_REFRESH', result['freshness_state'])

    def test_validated_conditional_live_response_recomputes_state(self):
        now = datetime.now(timezone.utc).isoformat()
        source = {'name': 'osm', 'endpoint': 'https://conditional.test/interpreter',
                  'kind': 'overpass', 'max_snapshot_age_seconds': 86400,
                  'rate_limit_per_second': 1, 'allowed_uses': ['internal'],
                  'commercial_use': False, 'reliability_weight': .8}
        request = Request(Area(29, 31, 30, 32), 'pharmacy', 'internal',
                          operator_contact='https://example.test/contact')
        payload = {'osm3s': {'timestamp_osm_base': now}, 'elements': [
            {'type': 'node', 'id': 1, 'lat': 29.5, 'lon': 31.5, 'tags': {'amenity': 'pharmacy'}}]}
        pinned = describe(source, request, payload, 'pinned_capture_not_live')
        self.assertEqual('HISTORICAL', pinned['freshness_state'])
        records = parse_overpass_payload(source, request, payload)
        with patch('poi_harvester.sources._robots_allowed', return_value=True), patch(
                'poi_harvester.sources._get_json', return_value=(None, {'snapshot': pinned})):
            result, cache = _overpass(source, request, prior_records=records)
        self.assertEqual('CURRENT', cache['snapshot']['freshness_state'])
        self.assertEqual(pinned['snapshot_id'], cache['snapshot']['snapshot_id'])
        self.assertEqual(records, result)

    def test_timeout_reports_failed_refresh_without_output(self):
        with TemporaryDirectory() as tmp, patch('poi_harvester.cli.run', side_effect=TimeoutError('no stale fallback')):
            output = Path(tmp) / 'run'
            stream = StringIO()
            with redirect_stderr(stream):
                code = main(['run', '--bbox', '29', '31', '30', '32', '--category', 'pharmacy', '--out', str(output)])
            self.assertEqual(1, code)
            self.assertEqual('FAILED_REFRESH', json.loads(stream.getvalue())['freshness_state'])
            self.assertFalse(output.exists())

    def test_queue_is_deterministic_unrated_and_hash_bound(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'queue.json'
            dataset = build_review_dataset()
            first = write_review_queue(dataset, path)
            data = path.read_bytes()
            self.assertEqual(first, write_review_queue(dataset, path))
            self.assertEqual(data, path.read_bytes())
            self.assertEqual(30, len(first['entries']))
            self.assertTrue(all(x['rating'] is None and x['reviewer'] is None for x in first['entries']))
            self.assertTrue(path.with_suffix('.md').exists())

    def test_queue_human_review_keeps_full_denominator(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            dataset = build_review_dataset()
            (p/'dataset.json').write_text(json.dumps(dataset), encoding='utf-8')
            queue = write_review_queue(dataset, p/'queue.json')
            with patch('builtins.input', side_effect=['a', 'q']), patch('builtins.print'):
                result = review_names(p/'dataset.json', p/'ratings.json', p/'score.json', True, 'Test reviewer', p/'queue.json')
            self.assertEqual(100, result['total'])
            self.assertEqual(1, result['reviewed'])
            self.assertIsNone(result['complete_sample_score'])
            self.assertEqual(queue['entries'][0]['id'], json.loads((p/'ratings.json').read_text())['ratings'][0]['id'])

    def test_mismatched_queue_rejected_before_rating(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            dataset = build_review_dataset()
            (p/'dataset.json').write_text(json.dumps(dataset), encoding='utf-8')
            queue = write_review_queue(dataset, p/'queue.json')
            queue['dataset_hash'] = 'wrong'
            (p/'queue.json').write_text(json.dumps(queue), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'queue'):
                review_names(p/'dataset.json', p/'ratings.json', p/'score.json', True, 'Test reviewer', p/'queue.json')
            self.assertFalse((p/'ratings.json').exists())
