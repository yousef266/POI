"""The published schema keeps required fields and only populated optional fields."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import json
from os import environ
from poi_harvester.publish import _public_columns, _publication_values, _has_value, REQUIRED_PUBLIC_FIELDS, COLUMN_TYPES, publish_geoserver


class PublicSchemaTests(unittest.TestCase):
    def setUp(self):
        self.row={'stable_id':'internal-key', 'lat':21.5,'lon':39.2,'category':'amenity_bank',
                  'confidence':.8,'name_en':'Example','name_ar':None,'source_keys':['authored:node/1'],
                  'provenance':{'name_en':'authored:node/1','category':'authored:node/1'},
                  'phone':None,'hours':None,'address':None}

    def test_required_empty_canonical_fields_remain(self):
        columns=set(_public_columns([self.row]))
        self.assertTrue(REQUIRED_PUBLIC_FIELDS <= columns)
        self.assertTrue({'name_ar','phone','email','hours','alternate_names','address_city'} <= columns)

    def test_unused_optional_fields_are_hidden(self):
        columns=_public_columns([self.row])
        self.assertNotIn('footprint_ref',columns)
        self.assertNotIn('name_ar_method',columns)
        self.assertNotIn('original_name_ar',columns)
        self.assertNotIn('provenance_email',columns)

    def test_optional_fields_with_any_real_value_are_retained(self):
        second={**self.row,'footprint_ref':'authored:way/2','name_ar_method':'rules',
                'name_ar_version':'v1','name_ar_confidence':.48,'original_name_ar':'اسم أصلي'}
        columns=_public_columns([self.row,second])
        self.assertTrue({'footprint_ref','name_ar_method','name_ar_version','name_ar_confidence','original_name_ar'} <= set(columns))

    def test_optional_field_provenance_stays_when_populated(self):
        row={**self.row,'provenance':{**self.row['provenance'],'phone':'authored:node/2'}}
        self.assertIn('provenance_phone',_public_columns([row]))

    def test_identity_is_only_id_in_public_projection(self):
        columns=_public_columns([self.row])
        self.assertEqual('id',columns[0])
        self.assertNotIn('stable_id',columns)
        self.assertNotIn('is_active',columns)

    def test_empty_layer_keeps_required_schema(self):
        self.assertEqual({'id',*REQUIRED_PUBLIC_FIELDS},set(_public_columns([])))

    def test_false_zero_and_unicode_values_are_not_discarded(self):
        self.assertTrue(all(_has_value(x) for x in (False,0,'بنك')))
        self.assertFalse(any(_has_value(x) for x in (None,' ','[]','{}',[],{})))

    def test_projection_is_deterministic_and_preserves_internal_evidence(self):
        original=deepcopy(self.row)
        self.assertEqual(_public_columns([self.row]),_public_columns([self.row]))
        self.assertEqual(set(COLUMN_TYPES),set(_publication_values(self.row)))
        self.assertEqual(original,self.row)

    def test_geoserver_schema_update_exposes_integer_id_and_selected_fields(self):
        columns=_public_columns([self.row])
        with patch.dict(environ,{'PGHOST':'example.test','PGUSER':'fixture','PGPASSWORD':'authored'}),patch('poi_harvester.publish._geoserver_request',return_value=b'{}') as request,patch('poi_harvester.publish._verify_wms_layer'):
            publish_geoserver('poi_bank',{'published_columns':columns},'db','ws')
        bodies=[json.loads(call.args[2]) for call in request.call_args_list if call.args[0]=='PUT' and 'featuretypes' in call.args[1]]
        attributes=bodies[0]['featureType']['attributes']['attribute']
        self.assertEqual({'name':'id','binding':'java.lang.Integer'},attributes[0])
        self.assertEqual(set(columns)|{'geom'},{x['name'] for x in attributes})
        self.assertNotIn('stable_id',{x['name'] for x in attributes})
        self.assertEqual('java.sql.Timestamp',next(x['binding'] for x in attributes if x['name']=='harvested_at'))
        reopen=[json.loads(call.args[2])['dataStore']['enabled'] for call in request.call_args_list if call.args[0]=='PUT' and 'datastores' in call.args[1] and 'featuretypes' not in call.args[1]]
        self.assertEqual([False,True],reopen)
