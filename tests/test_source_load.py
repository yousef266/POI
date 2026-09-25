from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import os
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from poi_harvester.sources import TokenBucket, _get_json, _robots_allowed


class _Response:
    status = 200
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"elements": []}'


class SourceLoadTests(unittest.TestCase):
    def test_four_processes_obey_one_aggregate_source_ceiling(self):
        with TemporaryDirectory() as temp:
            environment = os.environ.copy()
            environment["POI_RATE_STATE_PATH"] = str(Path(temp) / "rate.sqlite3")
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            code = ("from poi_harvester.sources import TokenBucket; import time; "
                    "TokenBucket(5, 'https://rate-test.invalid/source').wait(); print(time.time())")

            def worker(_index):
                completed = subprocess.run([sys.executable, "-c", code],
                                           env=environment, capture_output=True, text=True,
                                           check=True, timeout=15)
                return float(completed.stdout.strip())

            with ThreadPoolExecutor(max_workers=4) as pool:
                starts = sorted(pool.map(worker, range(4)))
            self.assertEqual(len(starts), 4)
            self.assertTrue(all(next_at - first_at >= 0.17
                                for first_at, next_at in zip(starts, starts[1:])), starts)

    def test_retry_after_and_exponential_backoff(self):
        url = "https://example.test/api"
        too_many = HTTPError(url, 429, "Too Many Requests", {"Retry-After": "3"}, None)
        with patch("poi_harvester.sources.urlopen", side_effect=[too_many, _Response()]), \
                patch("poi_harvester.sources.sleep") as sleeper, \
                patch.object(TokenBucket, "wait"):
            payload, _ = _get_json(url, TokenBucket(10), "honest-agent")
        self.assertEqual(payload, {"elements": []})
        sleeper.assert_called_once_with(3.0)

        with patch("poi_harvester.sources.urlopen", side_effect=[URLError("temporary"), _Response()]), \
                patch("poi_harvester.sources.sleep") as sleeper, \
                patch.object(TokenBucket, "wait"):
            _get_json(url, TokenBucket(10), "honest-agent")
        sleeper.assert_called_once_with(1)

    def test_robots_rate_limit_fails_closed(self):
        url = "https://example.test/robots.txt"
        with patch("poi_harvester.sources.urlopen",
                   side_effect=HTTPError(url, 429, "Too Many Requests", {}, None)):
            with self.assertRaisesRegex(RuntimeError, "rate limited"):
                _robots_allowed("https://example.test/api", "honest-agent")


if __name__ == "__main__":
    unittest.main()
