import io
import json
import unittest
from unittest.mock import patch

from bose_bridge.metadata import lookup_station


class DummyResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestMetadata(unittest.TestCase):
    def test_lookup_station_returns_station_data(self):
        response = DummyResponse(json.dumps([
            {"name": "Test Station", "favicon": "http://favicon.example/icon.png"}
        ]).encode())

        with patch("bose_bridge.metadata.urllib.request.urlopen", return_value=response):
            result = lookup_station("http://example.com/stream")

        self.assertEqual(result, {
            "name": "Test Station",
            "favicon": "http://favicon.example/icon.png",
        })

    def test_lookup_station_returns_empty_when_no_station(self):
        response = DummyResponse(b"[]")

        with patch("bose_bridge.metadata.urllib.request.urlopen", return_value=response):
            result = lookup_station("http://unknown-stream.example")

        self.assertEqual(result, {})

    def test_lookup_station_skips_failures(self):
        response = DummyResponse(json.dumps([
            {"name": "Failover Station", "favicon": "http://favicon.fail/icon.png"}
        ]).encode())

        with patch("bose_bridge.metadata.urllib.request.urlopen", side_effect=[Exception("bad"), response]):
            result = lookup_station("http://retry.example")

        self.assertEqual(result, {
            "name": "Failover Station",
            "favicon": "http://favicon.fail/icon.png",
        })


if __name__ == "__main__":
    unittest.main()
