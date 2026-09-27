"""Older available data is disclosed, while snapshot downgrade protection remains."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from poi_harvester.core import Area, Request
from poi_harvester.snapshots import describe, compare, validate_age
from poi_harvester.sources import load_registry, _overpass
from poi_harvester.pipeline import run, replay


class LatestAvailableTests(unittest.TestCase):
    def setUp(self):
        self.source = dict(name='authored', kind='overpass', endpoint='https://example.test/api',
                           auth_mode='none', license='authored fixture', attribution='fixture',
                           allowed_uses=['internal'], commercial_use=False, coverage_bbox=None,
                           freshness='fixture', rate_limit_per_second=1, reliability_weight=.8,
                           max_snapshot_age_seconds=86400, freshness_policy='latest_available')
        self.request = Request(Area(21,39,22,40), 'amenity_bank', 'internal', 'contact@example.test')
        self.payload = {'osm3s': {'timestamp_osm_base': '2026-07-15T00:00:00Z'},
                        'elements': [{'type':'node','id':1,'lat':21.5,'lon':39.5,
                                      'tags':{'amenity':'bank','name':'Example Bank'}}]}
        self.now = datetime(2026,9,28,tzinfo=timezone.utc)

    def test_old_response_accepted_and_disclosed_not_fresh(self):
        d = describe(self.source,self.request,self.payload,now=self.now)
        self.assertEqual('STALE',d['freshness_state'])
        self.assertEqual('OLDER_DATA_ACCEPTED_WITH_DISCLOSURE',d['freshness'])
        self.assertIn(d['timestamp'],d['freshness_notice'])
        self.assertIn('not a claim about all providers',d['availability_scope'])

    def test_strict_override_still_rejects_old_data(self):
        with self.assertRaisesRegex(RuntimeError,'Stale'):
            describe({**self.source,'freshness_policy':'strict'},self.request,self.payload,now=self.now)

    def test_latest_policy_never_allows_snapshot_downgrade(self):
        old = describe(self.source,self.request,self.payload,now=self.now)
        new = describe(self.source,self.request,{**self.payload,'osm3s':{'timestamp_osm_base':'2026-07-24T00:00:00Z'}},now=self.now)
        with self.assertRaisesRegex(RuntimeError,'older'):
            compare(old,new)

    def test_missing_future_and_malformed_timestamps_not_relaxed(self):
        for stamp in (None,'bad','2027-01-01T00:00:00Z'):
            with self.assertRaises(ValueError):
                describe(self.source,self.request,{**self.payload,'osm3s':{'timestamp_osm_base':stamp}},now=self.now)

    def test_conditional_response_keeps_old_data_disclosure(self):
        with patch('poi_harvester.sources._robots_allowed',return_value=True), patch('poi_harvester.sources._get_json',return_value=(self.payload,{})):
            rows, cache = _overpass(self.source,self.request)
        with patch('poi_harvester.sources._robots_allowed',return_value=True), patch('poi_harvester.sources._get_json',return_value=(None,cache)):
            _,again = _overpass(self.source,self.request,cache,rows)
        self.assertEqual('OLDER_DATA_ACCEPTED_WITH_DISCLOSURE',again['snapshot']['freshness'])
        self.assertEqual('STALE',again['snapshot']['freshness_state'])

    def test_old_data_pipeline_and_offline_replay(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp); registry=root/'registry.json'
            registry.write_text(json.dumps({'sources':[self.source]}),encoding='utf-8')
            with patch('poi_harvester.sources._robots_allowed',return_value=True),patch('poi_harvester.sources._get_json',return_value=(self.payload,{})):
                result=run(self.request,registry,root/'run',{'authored'})
            self.assertEqual(1,result['feature_count'])
            self.assertEqual('STALE',result['metadata']['source_snapshots']['authored']['freshness_state'])
            with patch('poi_harvester.sources.urlopen',side_effect=AssertionError('Replay must stay offline')):
                self.assertTrue(replay(root/'run')['identical'])

    def test_included_sources_choose_latest_available_and_invalid_policy_rejected(self):
        sources=load_registry(Path(__file__).resolve().parents[1]/'sources.json')
        self.assertTrue(all(s['freshness_policy']=='latest_available' for s in sources if s['kind']=='overpass'))
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'registry.json'
            p.write_text(json.dumps({'sources':[{**self.source,'freshness_policy':'wrong'}]}),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'freshness policy'):
                load_registry(p)
