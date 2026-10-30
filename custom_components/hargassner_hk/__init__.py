"""Hargassner HK: local + cloud integration for Hargassner wood chip boilers."""
from __future__ import annotations

from dataclasses import dataclass
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .cloud import HargassnerCloud
from .const import (
    ATTR_AMOUNT,
    ATTR_COMPONENT,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_HOURS,
    CONF_ALLOW_CLOUD_WRITE,
    CONF_BULK_DENSITY,
    CONF_CALORIFIC_VALUE,
    CONF_CLOUD_INTERVAL,
    CONF_DAQ_XML,
    CONF_STREAM_EXTRAS,
    CONF_TEMPLATE_SOURCE,
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
    SERVICE_SET_OPERATING_HOURS,
    SERVICE_SET_STORAGE,
)
from .coordinator import CloudCoordinator, LocalCoordinator, fuel_store, runtime_store
from .runtime import PROFILE_WOOD_CHIP, RuntimeTracker, available_counters, is_wood_chip
from .daq import DaqFormat, DaqFormatError, fit_to_stream, parse_daq_xml, with_stream_extras
from .templates import detect_template, is_builtin, load_builtin_templates
from .fuel import FuelSettings, FuelTracker
from .telnet import HargassnerTelnet

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
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
    options: dict


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

    async def _set_counter(call: ServiceCall) -> None:
        local = _local(call)
        if not local.runtime.has_counter(call.data[ATTR_COMPONENT]):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="unknown_component")
        local.runtime.set_counter(call.data[ATTR_COMPONENT], call.data[ATTR_HOURS])
        await local.async_save_fuel_now()
        local.async_update_listeners()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_OPERATING_HOURS,
        _set_counter,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
                vol.Required(ATTR_COMPONENT): cv.string,
                vol.Required(ATTR_HOURS): vol.All(vol.Coerce(float), vol.Range(min=0, max=1_000_000)),
            }
        ),
    )
    hass.services.async_register(DOMAIN, SERVICE_REFILL, _refill, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_STORAGE, _set_storage, schema=SERVICE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HargassnerHKConfigEntry) -> bool:
    """Set up a boiler from a config entry."""
    try:
        base_fmt = parse_daq_xml(entry.data[CONF_DAQ_XML])
        fmt = with_stream_extras(base_fmt, entry.data.get(CONF_STREAM_EXTRAS, []))
    except DaqFormatError as err:
        # Stored data is inconsistent: retrying cannot help, the user has to reconfigure.
        raise ConfigEntryError(f"Invalid DAQ template or stream correction: {err}") from err

    power_name = entry.options.get(CONF_POWER_CHANNEL, DEFAULT_POWER_CHANNEL)
    power_channel = fmt.analog_by_name(power_name) if power_name else None
    if power_name and power_channel is None:
        _LOGGER.warning("Output channel '%s' not in DAQ template, heat/fuel figures disabled", power_name)

    store = fuel_store(hass, entry.entry_id)
    fuel = FuelTracker(fuel_settings(entry), await store.async_load())

    rt_store = runtime_store(hass, entry.entry_id)
    digital_keys = {ch.key for ch in fmt.digital}
    runtime = RuntimeTracker(
        available_counters({ch.key for ch in fmt.analog}, digital_keys),
        await rt_store.async_load(),
        profile=PROFILE_WOOD_CHIP if is_wood_chip(digital_keys) else None,
    )
    # Every frame (~1/s) goes to the operating hours: short feed screw pulses would be missed otherwise
    client = HargassnerTelnet(
        entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT), fmt, on_frame=runtime.add_frame
    )
    client.start()
    if not await client.wait_for_frame(FIRST_FRAME_TIMEOUT):
        await client.stop()
        # The stream layout changed (firmware update, storage calculation switched on/off).
        # Only act on a length seen repeatedly, never on a single garbled line.
        length = client.last_rejected_length
        if length is not None and client.rejected_streak >= 3:
            update: dict = {}
            if is_builtin(entry.data):
                # Template was chosen automatically: re-detect among the shipped ones
                templates = await hass.async_add_executor_job(load_builtin_templates)
                if detection := detect_template(templates, length):
                    update = {
                        CONF_DAQ_XML: detection.xml,
                        CONF_STREAM_EXTRAS: list(detection.extras),
                        CONF_TEMPLATE_SOURCE: detection.source,
                    }
            elif (extras := fit_to_stream(base_fmt, length)) is not None:
                update = {CONF_STREAM_EXTRAS: list(extras)}  # user template: only adapt the correction
            if update and any(entry.data.get(k) != v for k, v in update.items()):
                _LOGGER.warning("Boiler stream layout changed (%s values), adapting: %s", length, update.get(CONF_TEMPLATE_SOURCE, update))
                hass.config_entries.async_update_entry(entry, data={**entry.data, **update})
                raise ConfigEntryNotReady("Boiler stream layout changed, template adapted, retrying")
        if client.frames_rejected:
            reason = (
                f"pm line has {client.last_rejected_length} values, "
                f"DAQ template expects {fmt.expected_length}"
            )
        else:
            reason = client.last_error or "no pm line received"
        raise ConfigEntryNotReady(f"No valid data from {client.host}:{client.port}: {reason}")

    # From here on the telnet task runs; stop it if anything below fails (incl. cancellation),
    # otherwise every setup retry would leave another connection open.
    try:
        local = LocalCoordinator(
            hass,
            entry,
            client,
            fuel,
            store,
            power_channel.key if power_channel else None,
            int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)),
            runtime,
            rt_store,
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

        entry.runtime_data = HargassnerHKData(fmt=fmt, local=local, cloud=cloud, options=dict(entry.options))
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await client.stop()
        raise
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: HargassnerHKConfigEntry) -> None:
    # Reconfigure/reauth already reload via async_update_reload_and_abort; only react to options.
    # The cloud write switch is read live by the coordinator and needs no reload.
    def relevant(options: dict) -> dict:
        return {k: v for k, v in options.items() if k != CONF_ALLOW_CLOUD_WRITE}

    if relevant(dict(entry.options)) != relevant(entry.runtime_data.options):
        await hass.config_entries.async_reload(entry.entry_id)
    else:
        entry.runtime_data.options = dict(entry.options)


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
    await runtime_store(hass, entry.entry_id).async_remove()
