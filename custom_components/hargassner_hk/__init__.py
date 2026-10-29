"""Hargassner HK: local + cloud integration for Hargassner wood chip boilers."""
from __future__ import annotations

from dataclasses import dataclass
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .cloud import HargassnerCloud
from .const import (
    ATTR_AMOUNT,
    ATTR_CONFIG_ENTRY_ID,
    CONF_BULK_DENSITY,
    CONF_CALORIFIC_VALUE,
    CONF_CLOUD_INTERVAL,
    CONF_DAQ_XML,
    CONF_EFFICIENCY,
    CONF_INSTALLATION_ID,
    CONF_NOMINAL_POWER,
    CONF_POWER_CHANNEL,
    CONF_UPDATE_INTERVAL,
    CONF_USE_CLOUD,
    DEFAULT_BULK_DENSITY,
    DEFAULT_CALORIFIC_VALUE,
    DEFAULT_CLOUD_INTERVAL,
    DEFAULT_EFFICIENCY,
    DEFAULT_NOMINAL_POWER,
    DEFAULT_POWER_CHANNEL,
    DEFAULT_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SERVICE_REFILL,
    SERVICE_SET_STORAGE,
)
from .coordinator import CloudCoordinator, LocalCoordinator, fuel_store
from .daq import DaqFormat, DaqFormatError, parse_daq_xml
from .fuel import FuelSettings, FuelTracker
from .telnet import HargassnerTelnet

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]
FIRST_FRAME_TIMEOUT = 20.0

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_AMOUNT): vol.All(vol.Coerce(float), vol.Range(min=0, max=10000)),
    }
)


@dataclass
class HargassnerHKData:
    """Runtime data of a config entry."""

    fmt: DaqFormat
    local: LocalCoordinator
    cloud: CloudCoordinator | None


type HargassnerHKConfigEntry = ConfigEntry[HargassnerHKData]


def fuel_settings(entry: ConfigEntry) -> FuelSettings:
    """Fuel parameters from the entry options."""
    opts = entry.options
    return FuelSettings(
        nominal_power_kw=float(opts.get(CONF_NOMINAL_POWER, DEFAULT_NOMINAL_POWER)),
        calorific_value_kwh_per_kg=float(opts.get(CONF_CALORIFIC_VALUE, DEFAULT_CALORIFIC_VALUE)),
        bulk_density_kg_per_srm=float(opts.get(CONF_BULK_DENSITY, DEFAULT_BULK_DENSITY)),
        efficiency=float(opts.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)) / 100.0,
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services once for all entries."""

    def _local(call: ServiceCall) -> LocalCoordinator:
        entry = hass.config_entries.async_get_entry(call.data[ATTR_CONFIG_ENTRY_ID])
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_not_loaded"
            )
        return entry.runtime_data.local

    async def _refill(call: ServiceCall) -> None:
        local = _local(call)
        local.fuel.refill_srm(call.data[ATTR_AMOUNT])
        await local.async_save_fuel_now()
        local.async_update_listeners()

    async def _set_storage(call: ServiceCall) -> None:
        local = _local(call)
        local.fuel.set_storage_srm(call.data[ATTR_AMOUNT])
        await local.async_save_fuel_now()
        local.async_update_listeners()

    hass.services.async_register(DOMAIN, SERVICE_REFILL, _refill, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_STORAGE, _set_storage, schema=SERVICE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HargassnerHKConfigEntry) -> bool:
    """Set up a boiler from a config entry."""
    try:
        fmt = parse_daq_xml(entry.data[CONF_DAQ_XML])
    except DaqFormatError as err:
        raise ConfigEntryNotReady(f"Invalid DAQ template: {err}") from err

    power_name = entry.options.get(CONF_POWER_CHANNEL, DEFAULT_POWER_CHANNEL)
    power_channel = fmt.analog_by_name(power_name) if power_name else None
    if power_name and power_channel is None:
        _LOGGER.warning("Output channel '%s' not in DAQ template, heat/fuel figures disabled", power_name)

    store = fuel_store(hass, entry.entry_id)
    fuel = FuelTracker(fuel_settings(entry), await store.async_load())

    client = HargassnerTelnet(entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT), fmt)
    client.start()
    if not await client.wait_for_frame(FIRST_FRAME_TIMEOUT):
        await client.stop()
        if client.frames_rejected:
            reason = (
                f"pm line has {client.last_rejected_length} values, "
                f"DAQ template expects {fmt.expected_length}"
            )
        else:
            reason = client.last_error or "no pm line received"
        raise ConfigEntryNotReady(f"No valid data from {client.host}:{client.port}: {reason}")

    local = LocalCoordinator(
        hass,
        entry,
        client,
        fuel,
        store,
        power_channel.key if power_channel else None,
        int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)),
    )
    await local.async_config_entry_first_refresh()

    cloud: CloudCoordinator | None = None
    if entry.data.get(CONF_USE_CLOUD):
        api = HargassnerCloud(async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
        cloud = CloudCoordinator(
            hass,
            entry,
            api,
            str(entry.data[CONF_INSTALLATION_ID]),
            int(entry.options.get(CONF_CLOUD_INTERVAL, DEFAULT_CLOUD_INTERVAL)),
        )
        # The cloud is optional: local entities work even if it is down.
        await cloud.async_refresh()
        if not cloud.last_update_success:
            _LOGGER.warning("Hargassner cloud not reachable, cloud entities follow once it is")

    entry.runtime_data = HargassnerHKData(fmt=fmt, local=local, cloud=cloud)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: HargassnerHKConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HargassnerHKConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = entry.runtime_data
        await data.local.client.stop()
        await data.local.async_save_fuel_now()
        if data.cloud is not None:
            await data.cloud.api.logout()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the stored fuel data with the entry."""
    await fuel_store(hass, entry.entry_id).async_remove()
