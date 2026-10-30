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
