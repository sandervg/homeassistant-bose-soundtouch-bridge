import urllib.error
import urllib.request

host = "192.168.1.99"
xml = """<?xml version="1.0" encoding="UTF-8" ?>
<ContentItem source="INTERNET_RADIO" type="station" location="http://stream3.polskieradio.pl:8904" sourceAccount="" isPresetable="true">
  <itemName>PR3</itemName>
</ContentItem>
"""

req = urllib.request.Request(
    f"http://{host}:8090/select",
    data=xml.encode("utf-8"),
    headers={"Content-Type": "application/xml"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=5) as r:
        print("HTTP", r.status)
        print(r.read().decode("utf-8", "ignore"))
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode("utf-8", "ignore"))