"""The public run surface completes the database/styled-layer deliverable by default."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from unittest.mock import patch
import json
import unittest
from poi_harvester.cli import build_parser, main
from poi_harvester.agent import invoke


class DefaultPublicationTests(unittest.TestCase):
    def setUp(self):
        self.args=['run','--bbox','21','39','22','40','--category','amenity_bank']
        self.result={'status':'completed','feature_count':1,'metadata':{}}

    def test_parser_publishes_by_default_and_preview_is_explicit(self):
        self.assertTrue(build_parser().parse_args(self.args).publish)
        self.assertFalse(build_parser().parse_args(self.args+['--no-publish']).publish)
        self.assertTrue(build_parser().parse_args(self.args+['--publish']).publish)

    def test_cli_default_publishes_then_verifies_target_and_style(self):
        events=[]; out=StringIO()
        with patch('poi_harvester.cli.run',return_value=dict(self.result)),patch('poi_harvester.cli.require_publish_env'),patch('poi_harvester.cli.publish',side_effect=lambda *a: events.append(('publish',a)) or {'layer':'ws:poi_amenity_bank'}),patch('poi_harvester.cli.verify_local',side_effect=lambda *a: events.append(('verify',a)) or {'status':'passed'}),redirect_stdout(out):
            code=main(self.args+['--database','db','--workspace','ws','--schema','banks'])
        self.assertEqual(0,code)
        result=json.loads(out.getvalue())
        self.assertEqual('PUBLISHED_AND_VERIFIED',result['publication_status'])
        self.assertEqual(['publish','verify'],[x[0] for x in events])
        self.assertEqual(('poi_amenity_bank','db','ws','banks'),events[1][1][:4])

    def test_cli_missing_target_never_claims_final_completion(self):
        out=StringIO()
        with patch('poi_harvester.cli.run',return_value=dict(self.result)),patch('poi_harvester.cli.publish') as pub,redirect_stdout(out):
            code=main(self.args)
        self.assertEqual(2,code)
        result=json.loads(out.getvalue())
        self.assertEqual('needs_input',result['status'])
        self.assertEqual('PENDING_CONFIGURATION',result['publication_status'])
        self.assertIn('--database',result['question'])
        pub.assert_not_called()

    def test_cli_explicit_preview_does_not_publish(self):
        out=StringIO()
        with patch('poi_harvester.cli.run',return_value=dict(self.result)),patch('poi_harvester.cli.publish') as pub,patch('poi_harvester.cli.verify_local') as verify,redirect_stdout(out):
            code=main(self.args+['--no-publish'])
        self.assertEqual(0,code)
        self.assertEqual('EXPLICIT_FILE_ONLY_PREVIEW',json.loads(out.getvalue())['publication_status'])
        pub.assert_not_called();verify.assert_not_called()

    def test_cli_failed_verification_is_not_a_completed_deliverable(self):
        out=StringIO();err=StringIO()
        with patch('poi_harvester.cli.run',return_value=dict(self.result)),patch('poi_harvester.cli.require_publish_env'),patch('poi_harvester.cli.publish',return_value={}),patch('poi_harvester.cli.verify_local',side_effect=RuntimeError('WMS failed')),redirect_stdout(out),redirect_stderr(err):
            code=main(self.args+['--database','db','--workspace','ws'])
        self.assertEqual(1,code)
        self.assertEqual('',out.getvalue())
        self.assertEqual('failed',json.loads(err.getvalue())['status'])
        self.assertIn('WMS failed',json.loads(err.getvalue())['error'])
        self.assertEqual('FAILED',json.loads(err.getvalue())['publication_status'])
        self.assertNotIn('freshness_state',json.loads(err.getvalue()))

    def test_api_missing_server_configuration_asks_before_collecting(self):
        with patch('poi_harvester.agent.require_publish_env',side_effect=ValueError('Missing local service settings')),patch('poi_harvester.agent.run') as collect:
            result=invoke({'bbox':[21,39,22,40],'category':'amenity_bank','database':'db','workspace':'ws'})
        self.assertEqual('needs_input',result['status'])
        self.assertIn('.env',result['question'])
        collect.assert_not_called()

    def test_cli_missing_server_configuration_asks_before_collecting(self):
        out=StringIO()
        with patch('poi_harvester.cli.require_publish_env',side_effect=ValueError('Missing local service settings')),patch('poi_harvester.cli.run') as collect,redirect_stdout(out):
            code=main(self.args+['--database','db','--workspace','ws'])
        self.assertEqual(2,code)
        self.assertEqual('needs_input',json.loads(out.getvalue())['status'])
        self.assertIn('.env',json.loads(out.getvalue())['question'])
        collect.assert_not_called()

    def test_api_default_also_verifies_publication(self):
        with patch('poi_harvester.agent.require_publish_env'),patch('poi_harvester.agent.run',return_value=dict(self.result)),patch('poi_harvester.agent.publish',return_value={'layer':'ws:poi_amenity_bank'}) as pub,patch('poi_harvester.agent.verify_local',return_value={'status':'passed'}) as verify:
            result=invoke({'bbox':[21,39,22,40],'category':'amenity_bank','database':'db','workspace':'ws'})
        self.assertEqual('PUBLISHED_AND_VERIFIED',result['publication_status'])
        self.assertEqual('passed',result['publication_verification']['status'])
        pub.assert_called_once();verify.assert_called_once()
