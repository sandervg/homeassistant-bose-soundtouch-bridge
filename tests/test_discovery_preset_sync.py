import io
import socket
import unittest
from unittest.mock import MagicMock, patch

import bose_bridge.discovery as discovery
import bose_bridge.preset_sync as preset_sync


class DummyResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummySocket:
    def __init__(self, responses):
        self.responses = responses
        self.closed = False

    def settimeout(self, timeout):
        pass

    def sendto(self, msg, addr):
        pass

    def recvfrom(self, bufsize):
        if not self.responses:
            raise socket.timeout()
        return self.responses.pop(0)

    def close(self):
        self.closed = True


class TestDiscoveryPresetSync(unittest.TestCase):
    def test_discover_soundtouch_all_finds_soundtouch(self):
        response_data = (
            "HTTP/1.1 200 OK\r\n"
            "Location: http://example.local/desc.xml\r\n\r\n"
        ).encode()
        description = DummyResponse(b"Bose SoundTouch device description")
        dummy_socket = DummySocket([(response_data, ("192.168.1.42", 1900))])

        with patch("bose_bridge.discovery.socket.socket", return_value=dummy_socket), patch(
            "bose_bridge.discovery.urllib.request.urlopen", return_value=description
        ):
            hosts = discovery.discover_soundtouch_all()

        self.assertEqual(hosts, ["192.168.1.42"])

    def test_fetch_speaker_info_parses_device_info(self):
        xml = (
            '<info deviceID="ABC123">'
            '<name>Living Room</name>'
            '<type>SoundTouch 10</type>'
            '</info>'
        )
        with patch("bose_bridge.discovery.urllib.request.urlopen", return_value=DummyResponse(xml.encode())):
            device_id, friendly, model = discovery.fetch_speaker_info("host")

        self.assertEqual(device_id, "ABC123")
        self.assertEqual(friendly, "Living Room")
        self.assertEqual(model, "SoundTouch 10")

    def test_fetch_speaker_info_raises_if_device_id_missing(self):
        xml = '<info><name>Unknown</name><type>SoundTouch</type></info>'
        with patch("bose_bridge.discovery.urllib.request.urlopen", return_value=DummyResponse(xml.encode())):
            from bose_bridge.constants import BoseError
            with self.assertRaises(BoseError):
                discovery.fetch_speaker_info("host")

    def test_current_preset_url_parses_xml_location(self):
        xml = (
            '<presets>'
            '<preset id="1">'
            '<ContentItem location="http://stream.example/1">'
            '<itemName>One</itemName>'
            '</ContentItem>'
            '</preset>'
            '</presets>'
        )
        with patch("bose_bridge.preset_sync.urllib.request.urlopen", return_value=DummyResponse(xml.encode())):
            result = preset_sync._current_preset_url("host", 1)

        self.assertEqual(result, "http://stream.example/1")

    def test_current_preset_url_uses_regex_fallback(self):
        xml = '<preset id="1" location="http://stream.example/1"></preset>'
        with patch("bose_bridge.preset_sync.urllib.request.urlopen", return_value=DummyResponse(xml.encode())):
            result = preset_sync._current_preset_url("host", 1)

        self.assertEqual(result, "http://stream.example/1")

    def test_sync_presets_skips_matching_entries(self):
        with patch.object(preset_sync, "_current_preset_url", return_value="http://stream.example/1"), patch.object(
            preset_sync, "_store_preset"
        ) as store_preset, patch("bose_bridge.preset_sync.time.sleep", return_value=None):
            preset_sync.sync_presets("host", {1: {"url": "http://stream.example/1"}})

        store_preset.assert_not_called()

    def test_sync_presets_writes_missing_entries(self):
        side_effects = [None, "http://stream.example/1"]
        with patch.object(preset_sync, "_current_preset_url", side_effect=side_effects), patch.object(
            preset_sync, "_store_preset", return_value=True
        ) as store_preset, patch("bose_bridge.preset_sync.time.sleep", return_value=None):
            preset_sync.sync_presets("host", {1: {"url": "http://stream.example/1"}})

        store_preset.assert_called_once_with("host", 1, "http://stream.example/1", None)

    def test_discover_description_url_returns_avtransport_location(self):
        loc = "http://10.0.0.5:8200/upnp/desc.xml"
        responses = [
            (f"HTTP/1.1 200 OK\r\nLOCATION: {loc}\r\n\r\n".encode(), ("10.0.0.5", 1900)),
        ]
        avtransport_desc = b"<root><serviceId>urn:upnp-org:serviceId:AVTransport</serviceId></root>"
        with patch("bose_bridge.discovery.socket.socket", return_value=DummySocket(responses)), patch(
            "bose_bridge.discovery.urllib.request.urlopen",
            return_value=DummyResponse(avtransport_desc),
        ):
            found = discovery.discover_description_url("10.0.0.5")
        self.assertEqual(found, loc)

    def test_discover_description_url_ignores_other_hosts(self):
        responses = [
            (b"HTTP/1.1 200 OK\r\nLOCATION: http://9.9.9.9:8200/d.xml\r\n\r\n", ("9.9.9.9", 1900)),
        ]
        with patch("bose_bridge.discovery.socket.socket", return_value=DummySocket(responses)):
            found = discovery.discover_description_url("10.0.0.5")
        self.assertIsNone(found)

    def test_get_upnp_services_falls_back_to_ssdp_on_404(self):
        class Svc:
            def __init__(self, sid):
                self.service_id = sid

        class Dev:
            services = [Svc("urn:...:AVTransport"), Svc("urn:...:RenderingControl")]

        def device_side_effect(url):
            if "BO5EBO5E" in url:
                raise Exception("404 Not Found")
            return Dev()

        with patch("bose_bridge.discovery.upnpclient") as upnp, patch.object(
            discovery, "discover_description_url", return_value="http://10.0.0.5:8200/d.xml"
        ):
            upnp.Device.side_effect = device_side_effect
            av, rc = discovery.get_upnp_services("10.0.0.5", "ABCDEF")
        self.assertIn("AVTransport", av.service_id)
        self.assertIn("RenderingControl", rc.service_id)


if __name__ == "__main__":
    unittest.main()
