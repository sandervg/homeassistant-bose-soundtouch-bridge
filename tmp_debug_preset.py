import io
import re
from unittest.mock import patch

from bose_bridge.preset_sync import _current_preset_url

class DummyResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

xml = '<preset id="1" location="http://stream.example/1"></preset>'
print('xml:', xml)
print('regex match:', bool(re.search(rf'<preset id="1"[^>]*>(.*?)</preset>', xml, re.DOTALL)))

with patch('bose_bridge.preset_sync.urllib.request.urlopen', return_value=DummyResponse(xml.encode())):
    print('result:', _current_preset_url('host', 1))
