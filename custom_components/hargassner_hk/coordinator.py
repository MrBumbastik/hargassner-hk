"""Coordinators for the local stream and the cloud API."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .cloud import CloudAuthError, CloudError, HargassnerCloud
from .const import DOMAIN, FRAME_STALE_AFTER
from .daq import Frame
from .fuel import FuelTracker
from .telnet import HargassnerTelnet

if TYPE_CHECKING:
    from . import HargassnerHKConfigEntry

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_SAVE_DELAY = 60


def fuel_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Persistent storage for the fuel tracker."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.fuel")


class LocalCoordinator(DataUpdateCoordinator[Frame]):
    """Publishes the newest frame from the telnet stream at a fixed rate.

    The boiler sends a frame every second. Writing every frame to the recorder
    would bloat the database, so entities update at the configured interval.
    """

    config_entry: HargassnerHKConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: HargassnerHKConfigEntry,
        client: HargassnerTelnet,
        fuel: FuelTracker,
        store: Store[dict[str, Any]],
        power_key: str | None,
        interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} local {client.host}",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.fuel = fuel
        self.power_key = power_key
        self._store = store

    def save_fuel(self) -> None:
        self._store.async_delay_save(self.fuel.as_dict, STORAGE_SAVE_DELAY)

    async def async_save_fuel_now(self) -> None:
        await self._store.async_save(self.fuel.as_dict())

    async def _async_update_data(self) -> Frame:
        frame = self.client.latest
        now = dt_util.now()
        if frame is None or (dt_util.utcnow() - frame.received).total_seconds() > FRAME_STALE_AFTER:
            self.fuel.add_sample(None, now)
            reason = self.client.last_error or "no valid data"
            if self.client.last_rejected_length is not None and self.client.frames_received == 0:
                reason = (
                    f"data has {self.client.last_rejected_length} values, "
                    f"template expects {self.client.fmt.expected_length}"
                )
            raise UpdateFailed(f"No current data from boiler: {reason}")

        power = frame.analog.get(self.power_key) if self.power_key else None
        if self.fuel.add_sample(power if isinstance(power, float) else None, now):
            self.save_fuel()
        return frame


@dataclass
class CloudData:
    """Cloud widgets keyed by a stable widget id."""

    widgets: dict[str, dict[str, Any]]
    online: bool


class CloudCoordinator(DataUpdateCoordinator[CloudData]):
    """Polls the Hargassner cloud for writable parameters."""

    config_entry: HargassnerHKConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: HargassnerHKConfigEntry,
        api: HargassnerCloud,
        installation_id: str,
        interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} cloud {installation_id}",
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self.installation_id = installation_id

    async def _async_update_data(self) -> CloudData:
        try:
            await self.api.ensure_token()
            widgets, meta = await self.api.get_widgets(self.installation_id)
        except CloudAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except CloudError as err:
            raise UpdateFailed(str(err)) from err

        result: dict[str, dict[str, Any]] = {}
        for widget in widgets:
            widget_type = str(widget.get("widget", "UNKNOWN"))
            number = str(widget.get("number", "") or "")
            values = widget.get("values") if isinstance(widget.get("values"), dict) else {}
            parameters = widget.get("parameters") if isinstance(widget.get("parameters"), dict) else {}
            # Stable id: type + number, independent of the user-editable name
            widget_id = f"{widget_type}_{number}".lower().rstrip("_")
            if widget_id in result:
                widget_id = f"{widget_id}_{len(result)}"
            result[widget_id] = {
                "type": widget_type,
                "number": number,
                "name": values.get("name") or widget_type.replace("_", " ").title(),
                "values": values,
                "parameters": {k: v for k, v in parameters.items() if isinstance(v, dict)},
            }
        return CloudData(widgets=result, online=bool(meta.get("online_state", True)))

    async def async_set_value(self, resource: str, value: Any) -> None:
        try:
            await self.api.set_value(resource, value)
        except CloudError as err:
            raise HomeAssistantError(f"Hargassner cloud rejected the value: {err}") from err
        await self.async_request_refresh()
