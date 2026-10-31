"""Constants for the Hargassner HK (wood chip) integration."""
from __future__ import annotations

DOMAIN = "hargassner_hk"
MANUFACTURER = "Hargassner"
DEFAULT_MODEL = "Eco-HK"

# Local telnet stream
DEFAULT_PORT = 23
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0  # the boiler sends a frame roughly every second
RECONNECT_MIN_DELAY = 5.0
RECONNECT_MAX_DELAY = 60.0
FRAME_STALE_AFTER = 90  # seconds without a valid frame -> entities unavailable

# Cloud API (reverse-engineered from the Hargassner app)
API_BASE_URL = "https://web.hargassner.at/api"
API_LOGIN = "/auth/login"
API_LOGOUT = "/auth/logout"
API_REFRESH = "/auth/refresh"
API_INSTALLATIONS = "/installations"
API_WIDGETS = "/widgets"
CLIENT_ID = 2
CLIENT_SECRET = "F6ye9z5oLaqW6IkGtihTzBpdFM7EAnYdc1Kwoydl"
APP_BRANDING = "BRANDING_HARGASSNER"

# Config entry data
CONF_DAQ_XML = "daq_xml"
CONF_STREAM_EXTRAS = "stream_extras"  # template channels followed by unlisted stream values
CONF_TEMPLATE_SOURCE = "template_source"  # "builtin:<name>" or "user", see templates.py
CONF_MODEL = "model"
CONF_USE_CLOUD = "use_cloud"
CONF_INSTALLATION_ID = "installation_id"
CONF_INSTALLATION_NAME = "installation_name"

# Options
CONF_UPDATE_INTERVAL = "update_interval"
CONF_ALLOW_CLOUD_WRITE = "allow_cloud_write"
CONF_CLOUD_INTERVAL = "cloud_interval"
CONF_POWER_CHANNEL = "power_channel"
CONF_NOMINAL_POWER = "nominal_power"
CONF_CALORIFIC_VALUE = "calorific_value"
CONF_BULK_DENSITY = "bulk_density"
CONF_EFFICIENCY = "efficiency"

DEFAULT_UPDATE_INTERVAL = 10
DEFAULT_ALLOW_CLOUD_WRITE = False  # safety: writing to the boiler is opt-in
DEFAULT_CLOUD_INTERVAL = 120
DEFAULT_POWER_CHANNEL = "Leistung"
DEFAULT_NOMINAL_POWER = 30.0  # kW
# Wood chips, spruce, water content ~W30: ~3.4 kWh/kg, ~200-230 kg per SRM
DEFAULT_CALORIFIC_VALUE = 3.4  # kWh/kg
DEFAULT_BULK_DENSITY = 210.0  # kg/SRM
DEFAULT_EFFICIENCY = 90.0  # %

# Well-known channel names in the DAQ template
CHANNEL_STATE = "ZK"

# Wood chip boilers (Eco-HK). Shared by channels.py (entities) and runtime.py (hours).
WOOD_CHIP_MARKERS = frozenset({"ra_run", "er_run", "ar_run"})  # room discharge + grate drives
KEY_STATE = "zk"
KEY_IGNITION_HEATER = "z_heiz"
KEY_FIRING_ACTIVE = "feuerung_aktiv_f2"  # boiler's own "firing active" bit
KEY_FEED = "foerder"  # fuel feed rate %
# Codes seen on an Eco-HK 50 (V30.0HAR.f); others show as "other".
#  3, 4, 5: cold start recorded 31.10. against display photos (display clock ~3 min ahead):
#     3 "Zündung Start" (~15 s, draft fan purges, feed starts),
#     4 "Zündung" (display first shows "Brennk. füllen" while the feed fills the chamber
#       for ~2.5 min, then the ignition heater + blower run ~6 min),
#     5 "Leistungsbrand" (output jumps to 100 %, firing bit F2 follows ~15 s later).
#  7: recorded 30.10.: feed stops, O2 rises to air (20 %), firing bit drops, then code 1
#     -> burn-out of the remaining fuel. The boiler reports output 100 % meanwhile!
# The Eco-HK 20-60 service manual (chapter 4.2, analog state output) lists the full table:
#  1 AUS, 3 ZUENDPROBE (display: "Zündung Start"), 4 ZUENDUNG, 5 LEISTUNGSBRAND,
#  6 GLUTERHALTUNG, 7 AUSBRAND, 9 ENTASCHUNG (seen 31.10. with the ash discharge running),
#  10 STB, 11 HAND, 12 STUECKHOLZ_NOTBETRIEB; 2 and 8 are unused.
WOOD_CHIP_STATE_CODES = {
    1: "off", 3: "ignition_start", 4: "ignition", 5: "full_firing", 6: "ember_preservation",
    7: "burnout", 9: "ash_removal", 10: "safety_limiter_tripped", 11: "manual_operation",
    12: "log_wood_emergency",
}
WOOD_CHIP_FULL_FIRING = frozenset(code for code, key in WOOD_CHIP_STATE_CODES.items() if key == "full_firing")
CHANNEL_ERROR = "Störungs Nr"

UNIT_SRM = "SRM"

# Services
SERVICE_REFILL = "refill"
SERVICE_SET_STORAGE = "set_storage"
SERVICE_SET_OPERATING_HOURS = "set_operating_hours"
ATTR_COMPONENT = "component"
ATTR_HOURS = "hours"
ATTR_AMOUNT = "amount"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
