from concurrent.futures import ThreadPoolExecutor
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, Thread
from unittest.mock import patch
import json
import os
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from poi_harvester.core import Area, Request
from poi_harvester.pipeline import run
from poi_harvester.sources import _retry_after_seconds, load_registry


class SourcePolicyTests(unittest.TestCase):
    def test_long_and_date_retry_after_are_respected(self):
        self.assertEqual(_retry_after_seconds("120", 0), 120)
        with patch("poi_harvester.sources.time", return_value=1000):
            self.assertEqual(_retry_after_seconds(formatdate(1120, usegmt=True), 0), 120)
        self.assertEqual(_retry_after_seconds("bad", 2), 4)

    def test_registry_requires_explicit_endpoint_path_and_coverage(self):
        source = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))["sources"][0]
        for field in ("path", "coverage_bbox", "auth_mode", "commercial_use"):
            with self.subTest(field=field), TemporaryDirectory() as temp:
                incomplete = dict(source)
                del incomplete[field]
                path = Path(temp) / "registry.json"
                path.write_text(json.dumps({"sources": [incomplete]}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_registry(path)

    def test_disallowed_source_is_never_collected_and_exclusion_has_reason(self):
        with TemporaryDirectory() as temp, patch("poi_harvester.pipeline.collect") as collect:
            with self.assertRaisesRegex(RuntimeError, "not approved"):
                run(Request(Area(47.37, 8.52, 47.39, 8.55), "pharmacy", "commercial"),
                    ROOT / "sources.json", Path(temp) / "blocked", {"osm_swiss"})
            collect.assert_not_called()
            self.assertFalse((Path(temp) / "blocked").exists())

    def test_actual_local_http_arrivals_from_four_processes_obey_aggregate_limit(self):
        arrivals, mutex = [], Lock()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                with mutex:
                    arrivals.append(time.perf_counter())
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *_args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as temp:
                endpoint = f"http://127.0.0.1:{server.server_port}/fixture"
                environment = os.environ.copy()
                environment["POI_RATE_STATE_PATH"] = str(Path(temp) / "slots.sqlite3")
                environment["PYTHONPATH"] = str(ROOT / "src")
                code = ("from poi_harvester.sources import TokenBucket,_get_json; "
                        f"endpoint={endpoint!r}; bucket=TokenBucket(5,endpoint); "
                        "[_get_json(endpoint,bucket,'POIHarvester-local-fixture') for _ in range(2)]")
                def worker(_index):
                    return subprocess.run([sys.executable, "-c", code], env=environment,
                                          capture_output=True, text=True, check=True, timeout=15)
                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(worker, range(4)))
            starts = sorted(arrivals)
            self.assertEqual(len(starts), 8)
            # 10ms allowance only for loopback arrival/scheduler jitter; deterministic policy tests cover exact ceilings.
            self.assertTrue(all(right - left >= 0.19 for left, right in zip(starts, starts[1:])), starts)
            self.assertTrue(all(sum(left <= observed < left + 0.99 for observed in starts) <= 5 for left in starts), starts)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
