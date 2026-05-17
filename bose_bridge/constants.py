import os

# Constants
DISCOVERY_INTERVAL = 300
MAX_RETRIES = 3
RETRY_BACKOFF = 0.5

# Supervisor
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")
SUPERVISOR_URL = "http://supervisor"

# Radio Browser
RADIO_BROWSER_BASES = [
    "https://de1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
]

# SSDP
SSDP_ADDR = ("239.255.255.250", 1900)
SSDP_TARGET = "urn:schemas-upnp-org:device:MediaRenderer:1"

# Paths
OPTIONS_PATH = "/data/options.json"

# MIME types
MIME_HTML = 'text/html'
MIME_XML = 'application/xml'
MIME_JSON = 'application/json'
MIME_MP3 = 'audio/mpeg'

# XML Namespaces
XML_NS_UPNP_AV = "urn:schemas-upnp-org:metadata-1-0/AVT/"
XML_NS_DIDL_LITE = "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
XML_NS_DC = "http://purl.org/dc/elements/1.1/"
XML_NS_UPNP = "urn:schemas-upnp-org:metadata-1-0/upnp/"

# Error Handling
class BoseError(Exception):
    """Base class for Bose-related errors."""

class BoseConnectionError(BoseError):
    """Raised when connection to speaker fails."""

class NoURLAvailable(BoseError):
    """Raised when no URL is available for a preset."""
