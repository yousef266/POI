"""Synthetic speed never becomes evidence of real POI positions/throughput."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from poi_harvester.benchmark import benchmark_10000
from poi_harvester.evaluation import _throughput_criterion


class PerformanceEvidenceTests(unittest.TestCase):
    def test_fast_grid_is_not_a_real_poi_throughput_pass(self):
        result = _throughput_criterion({'kind': 'synthetic_fixture_pipeline_only',
                                        'complete_features_per_hour': 1_000_000}, 'authored probe')
        self.assertEqual('NOT_CERTIFIED', result['local_status'])
        self.assertEqual('NOT_CERTIFIED', result['official_status'])
        self.assertIn('invented locations', result['evidence'])

    def test_unavailable_or_slow_load_probe_still_fails(self):
        for speed in (None, {'complete_features_per_hour': 9_999}):
            self.assertEqual('FAIL', _throughput_criterion(speed, 'authored probe')['local_status'])

    def test_probe_report_explicitly_discloses_invented_geometry(self):
        with TemporaryDirectory() as tmp, patch('poi_harvester.benchmark.run',
                return_value={'feature_count': 10000, 'timings': {}}), patch(
                'poi_harvester.benchmark.replay', return_value={'identical': True, 'reproducibility_hash': 'authored'}):
            root = Path(tmp)
            result = benchmark_10000(root)
            self.assertEqual(10000, result['features'])
            self.assertEqual(0, result['real_poi_count'])
            self.assertFalse(result['real_source_harvesting_included'])
            self.assertFalse(result['real_world_geometry_accuracy_verified'])
            self.assertEqual('INVENTED_GRID_NOT_REAL_POI_LOCATIONS', result['geometry_fixture_status'])
            self.assertEqual('SYNTHETIC_LOAD_TEST_ONLY', result['performance_evidence_kind'])
            self.assertEqual('NOT_CERTIFIED', result['a11_evidence_status'])
            data = json.loads((root / 'source.json').read_text(encoding='utf-8'))
            self.assertEqual(10000, len(data))
            self.assertTrue(all(x['geometry_method'] == 'fixture_synthetic' for x in data))
