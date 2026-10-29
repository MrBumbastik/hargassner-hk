"""Diagnostics: template layout, last raw line and connection statistics."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import HargassnerHKConfigEntry
from .const import CONF_DAQ_XML, CONF_INSTALLATION_ID

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, CONF_INSTALLATION_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HargassnerHKConfigEntry
) -> dict[str, Any]:
    data = entry.runtime_data
    client = data.local.client
    frame = client.latest
    cloud = data.cloud
    return {
        "entry": async_redact_data({k: v for k, v in entry.data.items() if k != CONF_DAQ_XML}, TO_REDACT),
        "options": dict(entry.options),
        "template": {
            "analog_count": data.fmt.analog_count,
            "digital_words": data.fmt.digital_count,
            "expected_length": data.fmt.expected_length,
            "analog": [[ch.index, ch.name, ch.unit] for ch in data.fmt.analog],
            "digital": [[ch.word, ch.bit, ch.name] for ch in data.fmt.digital],
        },
        "stream": {
            "connected": client.connected,
            "frames_received": client.frames_received,
            "frames_rejected": client.frames_rejected,
            "last_rejected_length": client.last_rejected_length,
            "last_error": client.last_error,
            "last_frame_time": frame.received.isoformat() if frame else None,
            "last_raw_line": frame.raw if frame else None,
            "power_channel": data.local.power_key,
        },
        "fuel": data.local.fuel.as_dict(),
        "cloud": None
        if cloud is None
        else {
            "last_update_success": cloud.last_update_success,
            "online": cloud.data.online if cloud.data else None,
            "widgets": {
                wid: {"type": w["type"], "values": w["values"], "parameters": sorted(w["parameters"])}
                for wid, w in (cloud.data.widgets.items() if cloud.data else [])
            },
        },
    }
