import os
import unittest
from unittest.mock import patch

from bose_bridge.config import load_options


class TestConfig(unittest.TestCase):
    def test_load_options_from_env(self):
        env = {
            "BOSE_HOST": "192.168.1.42",
            "SYNC_PRESETS_ON_STARTUP": "false",
            "PRESET_1_URL": " http://example.com/stream `",
            "PRESET_1_NAME": "My Station",
            "PRESET_1_FAVICON": "http://example.com/favicon.png",
            "SPEAKERS_JSON": "[{\"host\": \"192.168.1.42\"}]",
        }
        with patch.dict(os.environ, env, clear=False), patch("os.path.exists", return_value=False):
            cfg = load_options()

        self.assertEqual(cfg["bose_host"], "192.168.1.42")
        self.assertFalse(cfg["sync_presets_on_startup"])
        self.assertEqual(cfg["preset_1_url"], "http://example.com/stream")
        self.assertEqual(cfg["preset_1_name"], "My Station")
        self.assertEqual(cfg["preset_1_favicon"], "http://example.com/favicon.png")
        self.assertEqual(cfg["speakers"], [{"host": "192.168.1.42"}])

    def test_load_options_invalid_speakers_json(self):
        env = {
            "SPEAKERS_JSON": "{not a valid json}",
        }
        with patch.dict(os.environ, env, clear=True), patch("os.path.exists", return_value=False):
            cfg = load_options()

        self.assertEqual(cfg["speakers"], [])
        self.assertTrue(cfg["sync_presets_on_startup"])


if __name__ == "__main__":
    unittest.main()
