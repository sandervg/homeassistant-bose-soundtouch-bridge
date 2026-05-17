import unittest

from bose_bridge.helpers import (
    _clean_url,
    _parse_ws_preset_id,
    build_didl,
    apply_preset_meta_overrides,
)


class TestHelpers(unittest.TestCase):
    def test_clean_url_strips_quotes_and_backticks(self):
        self.assertEqual(_clean_url("'http://example.com'"), "http://example.com")
        self.assertEqual(_clean_url('"http://example.com"'), "http://example.com")
        self.assertEqual(_clean_url("`http://example.com`"), "http://example.com")
        self.assertEqual(_clean_url(None), "")

    def test_parse_ws_preset_id_with_now_selection_updated(self):
        xml = """
            <updates>
              <nowSelectionUpdated>
                <preset id="2" />
              </nowSelectionUpdated>
            </updates>
        """
        self.assertEqual(_parse_ws_preset_id(xml), 2)

    def test_parse_ws_preset_id_with_regex_fallback(self):
        msg = '<nowSelectionUpdated><preset id="4"></preset></nowSelectionUpdated>'
        self.assertEqual(_parse_ws_preset_id(msg), 4)

    def test_parse_ws_preset_id_returns_none_for_invalid(self):
        self.assertIsNone(_parse_ws_preset_id("<updates></updates>"))

    def test_build_didl_includes_title_and_url(self):
        xml = build_didl("http://stream.test/audio.mp3", {"name": "Test Station", "favicon": "http://icon.test/logo.png"})
        self.assertIn("<dc:title>Test Station</dc:title>", xml)
        self.assertIn("<upnp:albumArtURI>http://icon.test/logo.png</upnp:albumArtURI>", xml)
        self.assertIn("http://stream.test/audio.mp3", xml)

    def test_apply_preset_meta_overrides(self):
        cfg = {"preset_1_name": "My Station", "preset_1_favicon": "http://favicon.test/icon.png"}
        meta = {"name": "Default Name", "favicon": "http://old.test/icon.png"}
        result = apply_preset_meta_overrides(cfg, 1, meta)
        self.assertEqual(result["name"], "My Station")
        self.assertEqual(result["favicon"], "http://favicon.test/icon.png")


if __name__ == "__main__":
    unittest.main()
