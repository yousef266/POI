"""Authored fixtures for names, derived geometry, coherent snapshots and timeouts."""

from dataclasses import replace
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from threading import Event

from poi_harvester.core import Area, Request, canonicalize, conflate
from poi_harvester.enrichment import enrich_record
from poi_harvester.names import clean_name, arabic_key, resolve_osm_names
from poi_harvester.agent import invoke
from poi_harvester.pipeline import run, replay
from poi_harvester.snapshots import describe, compare, accept_latest, load_pinned, validate_age
from datetime import datetime, timezone
from poi_harvester.sources import parse_overpass_payload, _get_json, TokenBucket
from poi_harvester.intent import normalize_intent
from poi_harvester.place import CatalogPlaceResolver, choose_unique_place
from poi_harvester.publish import publish


class BlockerResolutionTests(unittest.TestCase):
    def setUp(self):
        self.source = {"name":"authored_osm", "kind":"overpass", "endpoint":"https://example.test/overpass",
                       "auth_mode":"none", "license":"project-authored fixture", "attribution":"fixture",
                       "allowed_uses":["internal"], "commercial_use":False, "coverage_bbox":None,
                       "freshness":"authored", "rate_limit_per_second":1, "reliability_weight":0.8}
        self.request = Request(Area(29.9,31.2,30.2,31.5),"pharmacy","internal")
        self.node = {"type":"node","id":1,"lat":30.05,"lon":31.25,
                     "tags":{"amenity":"pharmacy","official_name:ar":"صيدلية النخيل"}}
        self.payload = {"osm3s":{"timestamp_osm_base":"2026-07-15T00:00:00Z"},"elements":[self.node]}

    def test_authoritative_multilingual_alternate_is_mapped_and_provenanced(self):
        row = parse_overpass_payload(self.source,self.request,self.payload)[0]
        self.assertEqual("صيدلية النخيل",row["name_ar"])
        self.assertIn("tags.official_name:ar",row["provenance_name_ar"])
        enriched,_ = enrich_record(row,"authored_osm:node/1")
        self.assertEqual("Al Nakheel Pharmacy",enriched["name_en"])
        self.assertEqual(self.node,enriched["source_payload"])

    def test_genuinely_unnamed_is_preserved_without_bilingual_fabrication(self):
        node={**self.node,"tags":{"amenity":"pharmacy","operator":"Operator is not an establishment name"}}
        row=parse_overpass_payload(self.source,self.request,{**self.payload,"elements":[node]})[0]
        row,_=enrich_record(row,"authored_osm:node/1")
        self.assertIsNone(row["name_en"])
        self.assertIsNone(row["name_ar"])
        self.assertEqual("unnamed_source",row["name_status"])
        self.assertIn("name_fields",row["provenance_name_status"])

    def test_unicode_empty_malformed_and_alias_normalization(self):
        self.assertIsNone(clean_name(" \u200b\u200e \t"))
        self.assertIsNone(clean_name(12))
        self.assertEqual(arabic_key("صَيْدَلِيَّة الـنخيل"),arabic_key("صيدلية النخيل"))
        self.assertEqual(arabic_key("کریم"),arabic_key("كريم"))
        for text in ("صَيْدَلِيَّة النَّخِيل", "الصيدلية النخيل", "صيدلية الـنخيل"):
            first,_=enrich_record({"name_ar":text,"category":"pharmacy"},"fixture:1")
            second,_=enrich_record({"name_ar":text,"category":"pharmacy"},"fixture:1")
            self.assertEqual(first,second)
            self.assertEqual("Al Nakheel Pharmacy",first["name_en"])
            self.assertEqual(text,first["name_ar"])

    def test_existing_bilingual_values_and_whitespace_originals_preserved(self):
        source={"name_ar":"اسم المصدر","name_en":"Source Name","category":"pharmacy"}
        self.assertEqual(source,enrich_record(source,"fixture:1")[0])
        source={**source,"name_en":"  Source   Name  "}
        result,_=enrich_record(source,"fixture:1")
        self.assertEqual("Source Name",result["name_en"])
        self.assertEqual(source["name_en"],result["original_name_en"])

    def test_atm_grammar_is_translated_but_uncertain_proper_name_stays_uncertain(self):
        known,_=enrich_record({"name_en":"Al Nakheel ATM","category":"amenity_atm"},"fixture:1")
        self.assertEqual("صراف النخيل الآلي",known["name_ar"])
        restored,_=enrich_record({"name_ar":known["name_ar"],"category":"amenity_atm"},"fixture:1")
        self.assertEqual("Al Nakheel ATM",restored["name_en"])
        unknown,reason=enrich_record({"name_en":"Zyrol ATM","category":"amenity_atm"},"fixture:2")
        self.assertLess(unknown["name_ar_confidence"],0.6)
        self.assertIn("review",reason)

    def test_center_recovery_is_opt_in_derived_and_confidence_capped(self):
        way={"type":"way","id":9,"center":{"lat":30.05,"lon":31.25},"tags":{"amenity":"pharmacy","name":"Al Nakheel"}}
        payload={**self.payload,"elements":[way]}
        conservative=parse_overpass_payload(self.source,self.request,payload)[0]
        self.assertNotIn("lat",conservative)
        derived=parse_overpass_payload(self.source,replace(self.request,allow_source_centers=True),payload)[0]
        self.assertEqual(way["center"]["lat"],derived["lat"])
        self.assertTrue(derived["geometry_derived"])
        self.assertEqual("source_center_derived",derived["geometry_method"])
        self.assertLess(derived["geometry_confidence"],self.source["reliability_weight"])
        self.assertTrue(derived["geometry_provenance"].endswith(":center"))

    def test_invalid_center_remains_unresolved(self):
        for center in ({},{"lat":900,"lon":31.25},{"lat":None,"lon":31.25}):
            payload={**self.payload,"elements":[{"type":"way","id":9,"center":center,"tags":{"amenity":"pharmacy"}}]}
            row=parse_overpass_payload(self.source,replace(self.request,allow_source_centers=True),payload)[0]
            self.assertNotIn("lat",row)
            self.assertEqual("unresolved",row["geometry_status"])
            self.assertIn("source_payload",row)

    def test_snapshot_new_equal_old_missing_and_malformed_timestamps(self):
        previous=describe(self.source,self.request,self.payload)
        self.assertEqual("EQUAL_SNAPSHOT",compare(previous,previous))
        newer=describe(self.source,self.request,{**self.payload,"osm3s":{"timestamp_osm_base":"2026-07-16T00:00:00Z"}})
        self.assertEqual("NEWER_SNAPSHOT",compare(newer,previous))
        older=describe(self.source,self.request,{**self.payload,"osm3s":{"timestamp_osm_base":"2026-05-31T00:00:00Z"}})
        with self.assertRaisesRegex(RuntimeError,"older"):
            compare(older,previous)
        missing=describe(self.source,self.request,{"elements":[self.node]})
        self.assertEqual("UNVERIFIED_TIMESTAMP",compare(missing))
        with self.assertRaisesRegex(ValueError,"Missing"):
            compare(missing,previous)
        for stamp in ("invalid","2026-07-15",12):
            with self.assertRaises(ValueError):
                describe(self.source,self.request,{**self.payload,"osm3s":{"timestamp_osm_base":stamp}})

    def test_source_version_identity_and_equal_timestamp_hash_mismatches_rejected(self):
        descriptor=describe(self.source,self.request,self.payload)
        for field in ("source","endpoint","query_hash","dataset_hash"):
            with self.subTest(field=field),self.assertRaises(ValueError):
                compare({**descriptor,field:"different"},descriptor)
        with self.assertRaisesRegex(ValueError,"version"):
            describe(self.source,self.request,{**self.payload,"elements":[{**self.node,"version":-1}]})

    def test_durable_latest_snapshot_cannot_be_downgraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            source={**self.source,"snapshot_store":str(Path(tmp)/"snapshots.sqlite3")}
            newest=describe(source,self.request,self.payload)
            accept_latest(source,newest)
            older=describe(source,self.request,{**self.payload,"osm3s":{"timestamp_osm_base":"2026-05-31T00:00:00Z"}})
            with self.assertRaisesRegex(RuntimeError,"older"):
                accept_latest(source,older)
            self.assertEqual("EQUAL_SNAPSHOT",accept_latest(source,newest))

    def test_timeout_retry_budget_and_cancellation_never_fall_back(self):
        with patch("poi_harvester.sources.urlopen",side_effect=TimeoutError("read timed out")) as opener,patch("poi_harvester.sources.sleep"):
            with self.assertRaisesRegex(TimeoutError,"no stale fallback"):
                _get_json("https://example.test/data",TokenBucket(10),"authored",{"url":"https://example.test/data"},attempts=2)
            self.assertEqual(2,opener.call_count)
        event=Event();event.set()
        with patch("poi_harvester.sources.urlopen") as opener:
            with self.assertRaisesRegex(RuntimeError,"cancelled"):
                _get_json("https://example.test/data",TokenBucket(10),"authored",cancel_event=event)
            opener.assert_not_called()
        error=HTTPError("https://example.test/data",429,"rate limited",{"Retry-After":"120"},None)
        with patch("poi_harvester.sources.urlopen",side_effect=error) as opener,patch("poi_harvester.sources.sleep") as sleeper:
            with self.assertRaisesRegex(TimeoutError,"Retry-After"):
                _get_json("https://example.test/data",TokenBucket(10),"authored",total_timeout_seconds=5)
            self.assertEqual(1,opener.call_count)
            sleeper.assert_not_called()

    def test_timeout_preserves_existing_output_and_writes_no_false_removals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); registry=root/"sources.json"; output=root/"existing"
            registry.write_text(json.dumps({"sources":[self.source]}),encoding="utf-8")
            output.mkdir(); existing=output/"records.json"; existing.write_bytes(b"preserve-existing")
            with patch("poi_harvester.pipeline.collect",side_effect=TimeoutError("refresh timeout")):
                with self.assertRaisesRegex(RuntimeError,"Harvest incomplete"):
                    run(self.request,registry,output,{self.source["name"]})
            self.assertEqual(b"preserve-existing",existing.read_bytes())
            self.assertFalse((output/"changes.json").exists())
            self.assertFalse((output/"publication.json").exists())

    def test_equivalent_english_arabic_requests_pin_identical_dataset_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); registry=root/"sources.json"; catalog=root/"places.json"
            registry.write_text(json.dumps({"sources":[self.source]}),encoding="utf-8")
            catalog.write_text(json.dumps({"type":"FeatureCollection","features":[{"type":"Feature","properties":{"name":"Cairo","aliases":["القاهرة"],"id":"authored-boundary"},"geometry":{"type":"Polygon","coordinates":[[[31.2,29.9],[31.5,29.9],[31.5,30.2],[31.2,30.2],[31.2,29.9]]]}}]}),encoding="utf-8")
            requests=[]
            for text in ("I want all pharmacies in Cairo","عايز كل الصيدليات في القاهرة"):
                intent=normalize_intent(text)
                place=choose_unique_place(CatalogPlaceResolver(catalog,"internal"),intent["area"])
                requests.append(Request(place["area"],tuple(intent["categories"]),"internal",area_resolution=place["metadata"]))
            self.assertEqual(requests[0].area,requests[1].area)
            self.assertEqual(requests[0].categories,requests[1].categories)
            records=parse_overpass_payload(self.source,requests[0],self.payload)
            descriptor=describe(self.source,requests[0],self.payload,"pinned_capture_not_live")
            original=root/"original"
            run(requests[0],registry,original,{self.source["name"]},source_records_override={self.source["name"]:records},source_snapshots_override={self.source["name"]:descriptor})
            identities=[]; snapshots=[]
            with patch("poi_harvester.sources.urlopen",side_effect=AssertionError("Network prohibited")):
                for index,request in enumerate(requests):
                    pinned,versions=load_pinned(original,[self.source],request,{self.source["name"]})
                    target=root/f"language-{index}"
                    result=run(request,registry,target,{self.source["name"]},source_records_override=pinned,source_snapshots_override=versions)
                    rows=json.loads((target/"records.json").read_text(encoding="utf-8"))
                    identities.append({row["stable_id"] for row in rows})
                    snapshots.append(result["metadata"]["source_snapshots"][self.source["name"]]["snapshot_id"])
                    self.assertTrue(replay(target)["identical"])
                    self.assertTrue(replay(target)["identical"])
                self.assertEqual(identities[0],identities[1])
                self.assertEqual(snapshots[0],snapshots[1])
            saved=json.loads((original/"source_capture.json").read_text(encoding="utf-8"))
            saved[0]["records"][0]["source_payload"]["id"]=999
            (original/"source_capture.json").write_text(json.dumps(saved),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"integrity"):
                load_pinned(original,[self.source],requests[0],{self.source["name"]})

    def test_unverified_snapshot_cannot_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"records.json").write_text("[]",encoding="utf-8")
            (root/"metadata.json").write_text(json.dumps({"source_snapshots":{"test":{"timestamp":None}}}),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"Unverified"):
                publish(root,"poi_pharmacy","test","test")

    def test_snapshot_metadata_tampering_prevents_refresh_and_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); registry=root/"sources.json"; original=root/"original"
            registry.write_text(json.dumps({"sources":[self.source]}),encoding="utf-8")
            records=parse_overpass_payload(self.source,self.request,self.payload)
            descriptor=describe(self.source,self.request,self.payload,"pinned_capture_not_live")
            run(self.request,registry,original,{self.source["name"]},
                source_records_override={self.source["name"]:records},
                source_snapshots_override={self.source["name"]:descriptor})
            meta=json.loads((original/"metadata.json").read_text(encoding="utf-8"))
            meta["source_snapshots"][self.source["name"]]["timestamp"]="2026-07-16T00:00:00Z"
            (original/"metadata.json").write_text(json.dumps(meta),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"integrity"):
                publish(original,"poi_pharmacy","test","test")
            with self.assertRaisesRegex(ValueError,"integrity"):
                run(self.request,registry,root/"next",{self.source["name"]},original/"records.json",
                    source_records_override={self.source["name"]:records},
                    source_snapshots_override={self.source["name"]:descriptor})
            self.assertFalse((root/"next").exists())

    def test_duplicate_aliases_have_deterministic_unicode_keys(self):
        names=resolve_osm_names({"name:en":"Al Nakheel Pharmacy","name:ar":"صيدلية النخيل", "alt_name":"صَيْدَلِيَّة النخيل;Other;Other"},"fixture:1")
        self.assertEqual(["Other"],names["alternate_names"])
        self.assertEqual(names,resolve_osm_names({"alt_name":"Other;صَيْدَلِيَّة النخيل;Other", "name:ar":"صيدلية النخيل","name:en":"Al Nakheel Pharmacy"},"fixture:1"))

    def test_transport_stream_deadline_and_cooldown_are_bounded(self):
        class Response:
            status=200; headers={}
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read1(self,size): return b'{}'
        with patch("poi_harvester.sources.perf_counter",side_effect=[0,0,0,0,0,6]),patch("poi_harvester.sources.urlopen",return_value=Response()):
            with self.assertRaisesRegex(TimeoutError,"no stale fallback"):
                _get_json("https://example.test/data",TokenBucket(10),"authored",attempts=1,total_timeout_seconds=5)
        with tempfile.TemporaryDirectory() as tmp,patch.dict("os.environ",{"POI_RATE_STATE_PATH":str(Path(tmp)/"rate.sqlite3")}):
            limiter=TokenBucket(0.1,"https://example.test/data")
            with limiter.request_slot(): pass
            with self.assertRaisesRegex(TimeoutError,"cooldown"):
                with limiter.request_slot(remaining=lambda: 1):
                    self.fail("Must not dispatch before cooldown expires")

    def test_structured_interface_pins_and_preserves_latest_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); registry=root/"sources.json"; original=root/"original"
            registry.write_text(json.dumps({"sources":[self.source]}),encoding="utf-8")
            records=parse_overpass_payload(self.source,self.request,self.payload)
            descriptor=describe(self.source,self.request,self.payload,"pinned_capture_not_live")
            run(self.request,registry,original,{self.source["name"]},source_records_override={self.source["name"]:records},source_snapshots_override={self.source["name"]:descriptor})
            payload={"bbox":[29.9,31.2,30.2,31.5],"category":"pharmacy","publish":False,
                     "registry":str(registry),"sources":[self.source["name"]],"snapshot_from":str(original),
                     "snapshot_store":str(root/"store.sqlite3"),"output_dir":str(root/"api"),"allow_source_centers":True}
            with patch("poi_harvester.sources.urlopen",side_effect=AssertionError("No network for pinned API")):
                result=invoke(payload)
            self.assertEqual(1,result["metadata"]["feature_count"])
            self.assertEqual(descriptor["snapshot_id"],result["metadata"]["source_snapshots"][self.source["name"]]["snapshot_id"])
            self.assertTrue((root/"store.sqlite3").exists())

    def test_publication_metadata_discloses_derived_and_pinned_input(self):
        from poi_harvester.publish import publish_geoserver
        from os import environ
        metadata={"contributors":[{"attribution":"authored"}],"derived_geometry_count":1,
                  "source_snapshots":{"authored":{"timestamp":"2026-07-15T00:00:00Z","mode":"pinned_capture_not_live"}}}
        with patch.dict(environ,{"PGHOST":"localhost","PGUSER":"test","PGPASSWORD":"authored","GEOSERVER_URL":"http://localhost/geoserver"}),patch("poi_harvester.publish._geoserver_request",return_value={"exists":True}) as request,patch("poi_harvester.publish._verify_wms_layer"):
            publish_geoserver("poi_pharmacy",metadata,"test","test")
        abstracts=[json.loads(call.args[2])["featureType"]["abstract"] for call in request.call_args_list
                   if call.args[0]=="PUT" and "featuretypes" in call.args[1]]
        self.assertEqual(1,len(abstracts))
        self.assertIn("derived, not verified entrances",abstracts[0])
        self.assertIn("pinned_capture_not_live",abstracts[0])

    def test_live_age_policy_rejects_lag_missing_and_future_without_hiding_capture_age(self):
        source={**self.source,"max_snapshot_age_seconds":86400}
        now=datetime(2026,7,15,12,tzinfo=timezone.utc)
        descriptor=describe(source,self.request,self.payload,now=now)
        self.assertEqual("LIVE_AGE_POLICY_VALIDATED",descriptor["freshness"])
        for stamp,reason in (("2026-07-13T00:00:00Z","Stale"),(None,"missing"),("2026-07-16T00:00:00Z","future")):
            with self.subTest(stamp=stamp),self.assertRaisesRegex((ValueError,RuntimeError),reason):
                describe(source,self.request,{**self.payload,"osm3s":{"timestamp_osm_base":stamp}},now=now)
        pinned=describe(source,self.request,self.payload,"pinned_capture_not_live",now=datetime(2026,9,27,tzinfo=timezone.utc))
        self.assertEqual("HISTORICAL_CAPTURE_NOT_LIVE",pinned["freshness"])
        self.assertEqual(descriptor["snapshot_id"],pinned["snapshot_id"])
        with self.assertRaisesRegex(RuntimeError,"Stale"):
            validate_age(source,descriptor,datetime(2026,9,27,tzinfo=timezone.utc))

    def test_stale_live_age_rejection_precedes_state_changes_and_publication(self):
        from poi_harvester.sources import _overpass
        with tempfile.TemporaryDirectory() as tmp:
            source={**self.source,"max_snapshot_age_seconds":86400,"snapshot_store":str(Path(tmp)/"latest.sqlite3")}
            request=replace(self.request,operator_contact="https://example.test/contact")
            with patch("poi_harvester.sources._robots_allowed",return_value=True),patch("poi_harvester.sources._get_json",return_value=(self.payload,{})):
                with self.assertRaisesRegex(RuntimeError,"Stale"):
                    _overpass(source,request)
            self.assertFalse(Path(source["snapshot_store"]).exists())

    def test_api_default_age_policy_rejects_stale_live_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); registry=root/"sources.json"
            registry.write_text(json.dumps({"sources":[self.source]}),encoding="utf-8")
            payload={"bbox":[29.9,31.2,30.2,31.5],"category":"pharmacy","publish":False,
                     "registry":str(registry),"sources":[self.source["name"]],"contact":"https://example.test/contact",
                     "snapshot_store":str(root/"store.sqlite3"),"output_dir":str(root/"failed")}
            with patch("poi_harvester.sources._robots_allowed",return_value=True),patch("poi_harvester.sources._get_json",return_value=(self.payload,{})):
                result=invoke(payload)
            self.assertEqual("failed",result["status"])
            self.assertIn("Stale",result["error"])
            self.assertFalse((root/"failed").exists())
            self.assertFalse((root/"store.sqlite3").exists())

    def test_live_override_does_not_bypass_age_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); registry=root/"sources.json"
            registry.write_text(json.dumps({"sources":[self.source]}),encoding="utf-8")
            records=parse_overpass_payload(self.source,self.request,self.payload)
            descriptor=describe(self.source,self.request,self.payload)
            with self.assertRaisesRegex(RuntimeError,"Stale"):
                run(self.request,registry,root/"failed",{self.source["name"]},
                    source_records_override={self.source["name"]:records},
                    source_snapshots_override={self.source["name"]:descriptor},max_snapshot_age_seconds=86400)
            self.assertFalse((root/"failed").exists())

    def test_selected_authoritative_name_keeps_its_own_original_and_field_provenance(self):
        first={"id":"node/1","lat":30.05,"lon":31.25,"category":"pharmacy",
               "name_en":"Al Nakheel Pharmacy","name_ar":"صيدلية النخيل",
               "provenance_name_en":"generated:authored", "name_en_source_field":"generated",
               "original_name_en":"Generated input", "harvested_at":"2026-07-15T00:00:00Z"}
        second={**first,"id":"node/2","provenance_name_en":"source:official_name:en",
                "name_en_source_field":"official_name:en","original_name_en":"  Al Nakheel Pharmacy  "}
        merged=conflate([canonicalize(first,{**self.source,"reliability_weight":0.9}),canonicalize(second,self.source)])[0]
        self.assertEqual("source:official_name:en",merged["provenance"]["name_en"])
        self.assertEqual("official_name:en",merged["name_en_source_field"])
        self.assertEqual(second["original_name_en"],merged["original_name_en"])

    def test_derived_center_confidence_survives_normalization_and_conflation(self):
        way={"type":"way","id":9,"center":{"lat":30.05,"lon":31.25},"tags":{"amenity":"pharmacy","name":"Al Nakheel"}}
        raw=parse_overpass_payload(self.source,replace(self.request,allow_source_centers=True),{**self.payload,"elements":[way]})[0]
        row=conflate([canonicalize(raw,self.source)])[0]
        self.assertTrue(row["geometry_derived"])
        self.assertEqual(0.35,row["geometry_confidence"])
        self.assertEqual(0.35,row["confidence"])
        self.assertEqual(raw["geometry_provenance"],row["geometry_provenance"])

    def test_cli_cancellation_has_failure_exit_and_no_success_or_publication(self):
        from poi_harvester.cli import main
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        stdout=StringIO(); stderr=StringIO()
        with patch("poi_harvester.cli.run",side_effect=KeyboardInterrupt),patch("poi_harvester.cli.publish") as publisher,redirect_stdout(stdout),redirect_stderr(stderr):
            code=main(["run","--bbox","29.9","31.2","30.2","31.5","--category","pharmacy","--sources","openstreetmap"])
        self.assertEqual(130,code)
        self.assertEqual("cancelled",json.loads(stderr.getvalue())["status"])
        self.assertEqual("",stdout.getvalue())
        publisher.assert_not_called()

    def test_304_cannot_bypass_latest_snapshot_or_missing_evidence_guard(self):
        from poi_harvester.sources import _overpass
        with tempfile.TemporaryDirectory() as tmp:
            source={**self.source,"snapshot_store":str(Path(tmp)/"latest.sqlite3")}
            request=replace(self.request,operator_contact="https://example.test/contact")
            descriptor=describe(source,request,self.payload)
            accept_latest(source,describe(source,request,{**self.payload,"osm3s":{"timestamp_osm_base":"2026-07-16T00:00:00Z"}}))
            prior=parse_overpass_payload(source,request,self.payload)
            with patch("poi_harvester.sources._robots_allowed",return_value=True),patch("poi_harvester.sources._get_json",return_value=(None,{"snapshot":descriptor})):
                with self.assertRaisesRegex(RuntimeError,"older"):
                    _overpass(source,request,prior_records=prior)
            with patch("poi_harvester.sources._robots_allowed",return_value=True),patch("poi_harvester.sources._get_json",return_value=(None,{})):
                with self.assertRaisesRegex(RuntimeError,"verified full snapshot"):
                    _overpass(source,request,prior_records=prior)

    def test_304_reprocesses_full_source_capture_without_losing_unresolved_records(self):
        from poi_harvester.sources import _overpass
        way={"type":"way","id":9,"center":{"lat":30.05,"lon":31.25},"tags":{"amenity":"pharmacy","name":"Al Nakheel"}}
        payload={**self.payload,"elements":[self.node,way]}
        request=replace(self.request,operator_contact="https://example.test/contact",allow_source_centers=True)
        prior=parse_overpass_payload(self.source,self.request,payload)
        descriptor=describe(self.source,request,payload)
        with patch("poi_harvester.sources._robots_allowed",return_value=True),patch("poi_harvester.sources._get_json",return_value=(None,{"snapshot":descriptor})):
            rows,cache=_overpass(self.source,request,prior_records=prior)
        self.assertEqual({"node/1","way/9"},{r["id"] for r in rows})
        self.assertTrue(next(r for r in rows if r["id"]=="way/9")["geometry_derived"])
        self.assertEqual(descriptor["snapshot_id"],cache["snapshot"]["snapshot_id"])
        corrupted=[{**prior[0],"source_payload":{**self.node,"id":999}},prior[1]]
        with patch("poi_harvester.sources._robots_allowed",return_value=True),patch("poi_harvester.sources._get_json",return_value=(None,{"snapshot":descriptor})):
            with self.assertRaisesRegex(ValueError,"integrity"):
                _overpass(self.source,request,prior_records=corrupted)

    def test_http_200_partial_timeout_response_cannot_modify_snapshot_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); registry=root/"sources.json"; target=root/"existing"
            source={**self.source,"snapshot_store":str(root/"latest.sqlite3")}
            registry.write_text(json.dumps({"sources":[source]}),encoding="utf-8")
            target.mkdir(); (target/"records.json").write_bytes(b'preserve-existing')
            request=replace(self.request,operator_contact="https://example.test/contact")
            partial={**self.payload,"remark":"runtime error: Query timed out; partial elements returned"}
            with patch("poi_harvester.sources._robots_allowed",return_value=True),patch("poi_harvester.sources._get_json",return_value=(partial,{})):
                with self.assertRaisesRegex(RuntimeError,"Query timed out"):
                    run(request,registry,target,{source["name"]})
            self.assertEqual(b'preserve-existing',(target/"records.json").read_bytes())
            self.assertFalse((root/"latest.sqlite3").exists())
            self.assertFalse((target/"changes.json").exists())
            self.assertFalse((target/"publication.json").exists())

    def test_malformed_source_response_cannot_be_mistaken_for_empty_authoritative_dataset(self):
        from poi_harvester.sources import _overpass
        request=replace(self.request,operator_contact="https://example.test/contact")
        for payload in ({"osm3s":self.payload["osm3s"]},{**self.payload,"elements":None},[self.node]):
            with self.subTest(payload=payload),patch("poi_harvester.sources._robots_allowed",return_value=True),patch("poi_harvester.sources._get_json",return_value=(payload,{})):
                with self.assertRaisesRegex(RuntimeError,"elements array missing"):
                    _overpass(self.source,request)


if __name__ == "__main__":
    unittest.main()
