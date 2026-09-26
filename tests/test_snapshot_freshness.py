"""Regression for an older Overpass replica falsely deleting newer POIs."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from poi_harvester.core import Area, Request
from poi_harvester.pipeline import run
from poi_harvester.sources import _overpass, load_registry


class SnapshotFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.source = next(s for s in load_registry(Path("sources.json"))
                           if s["name"] == "openstreetmap")
        self.request = Request(Area(29.9, 31.2, 30.2, 31.5), "pharmacy", "internal",
                               "https://example.test/operator")
        self.previous = [{"id": "node/1", "source_version": "2026-07-15T15:22:01Z"}]

    def payload(self, timestamp):
        return {"osm3s": {"timestamp_osm_base": timestamp}, "elements": []}

    def test_older_snapshot_refuses_false_removals(self):
        with patch("poi_harvester.sources._robots_allowed", return_value=True), \
             patch("poi_harvester.sources._get_json", return_value=(self.payload("2026-05-31T22:37:44Z"), {})):
            with self.assertRaisesRegex(RuntimeError, "older than the previous capture"):
                _overpass(self.source, self.request, prior_records=self.previous)

    def test_equal_or_newer_snapshot_allows_real_removals(self):
        for timestamp in ("2026-07-15T15:22:01Z", "2026-07-16T00:00:00Z"):
            with self.subTest(timestamp=timestamp), \
                 patch("poi_harvester.sources._robots_allowed", return_value=True), \
                 patch("poi_harvester.sources._get_json", return_value=(self.payload(timestamp), {})):
                records, _ = _overpass(self.source, self.request, prior_records=self.previous)
                self.assertEqual([], records)

    def test_stale_refresh_writes_no_change_set_or_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous = root / "previous"
            previous.mkdir()
            (previous / "records.json").write_text("[]", encoding="utf-8")
            (previous / "http_cache.json").write_text("{}", encoding="utf-8")
            (previous / "raw.json").write_text(json.dumps([
                {"source": "openstreetmap", "record": self.previous[0]}]), encoding="utf-8")
            output = root / "new"
            with patch("poi_harvester.sources._robots_allowed", return_value=True), \
                 patch("poi_harvester.sources._get_json", return_value=(self.payload("2026-05-31T22:37:44Z"), {})):
                with self.assertRaisesRegex(RuntimeError, "Harvest incomplete"):
                    run(self.request, Path("sources.json"), output, {"openstreetmap"},
                        previous / "records.json")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
