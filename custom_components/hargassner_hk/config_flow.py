"""Config flow for Hargassner HK."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from .cloud import CloudAuthError, CloudError, HargassnerCloud
from .const import (
    CONF_BULK_DENSITY,
    CONF_CALORIFIC_VALUE,
    CONF_CLOUD_INTERVAL,
    CONF_DAQ_XML,
    CONF_EFFICIENCY,
    CONF_INSTALLATION_ID,
    CONF_INSTALLATION_NAME,
    CONF_MODEL,
    CONF_NOMINAL_POWER,
    CONF_POWER_CHANNEL,
    CONF_UPDATE_INTERVAL,
    CONF_USE_CLOUD,
    DEFAULT_BULK_DENSITY,
    DEFAULT_CALORIFIC_VALUE,
    DEFAULT_CLOUD_INTERVAL,
    DEFAULT_EFFICIENCY,
    DEFAULT_MODEL,
    DEFAULT_NOMINAL_POWER,
    DEFAULT_POWER_CHANNEL,
    DEFAULT_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .daq import DaqFormatError, decode_frame, extract_daq_xml, parse_daq_xml, split_pm_line
from .telnet import read_pm_line

_LOGGER = logging.getLogger(__name__)

NO_CHANNEL = "-"


def _local_schema(defaults: Mapping[str, Any], with_name: bool) -> vol.Schema:
    schema: dict[Any, Any] = {}
    if with_name:
        schema[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Hargassner Eco-HK"))] = str
    schema[vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED))] = str
    schema[vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT))] = vol.All(
        vol.Coerce(int), vol.Range(min=1, max=65535)
    )
    schema[vol.Required(CONF_DAQ_XML, default=defaults.get(CONF_DAQ_XML, vol.UNDEFINED))] = TextSelector(
        TextSelectorConfig(multiline=True)
    )
    return vol.Schema(schema)


def _cloud_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_USE_CLOUD, default=defaults.get(CONF_USE_CLOUD, False)): BooleanSelector(),
            vol.Optional(CONF_EMAIL, default=defaults.get(CONF_EMAIL, "")): TextSelector(
                TextSelectorConfig(type=TextSelectorType.EMAIL)
            ),
            vol.Optional(CONF_PASSWORD, default=""): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    )


async def _validate_local(user_input: dict[str, Any]) -> tuple[str, dict[str, str], dict[str, str]]:
    """Parse the template and check it against a live pm line.

    Returns (cleaned xml, errors, description placeholders).
    """
    try:
        xml = extract_daq_xml(user_input[CONF_DAQ_XML])
        fmt = parse_daq_xml(xml)
    except DaqFormatError as err:
        _LOGGER.debug("Invalid DAQ template: %s", err)
        return "", {CONF_DAQ_XML: "invalid_daq"}, {"error_detail": str(err)}

    try:
        line = await read_pm_line(user_input[CONF_HOST], user_input[CONF_PORT])
    except (OSError, TimeoutError, ConnectionError) as err:
        _LOGGER.debug("Cannot read pm line: %s", err)
        return xml, {"base": "cannot_connect"}, {}

    received = len(split_pm_line(line) or [])
    if decode_frame(fmt, line, dt_util.utcnow()) is None:
        return xml, {CONF_DAQ_XML: "template_mismatch"}, {
            "received": str(received),
            "expected": str(fmt.expected_length),
        }
    return xml, {}, {}


async def _cloud_login(hass: Any, email: str, password: str) -> tuple[list[dict[str, Any]], str | None]:
    api = HargassnerCloud(async_get_clientsession(hass), email, password)
    try:
        await api.login()
        installations = await api.get_installations()
    except CloudAuthError:
        return [], "invalid_auth"
    except CloudError:
        return [], "cloud_cannot_connect"
    finally:
        await api.logout()
    if not installations:
        return [], "no_installations"
    return installations, None


class HargassnerHKConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Hargassner wood chip boiler."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._title = ""
        self._installations: list[dict[str, Any]] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HargassnerHKOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"received": "?", "expected": "?", "error_detail": ""}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST].strip().lower())
            self._abort_if_unique_id_configured()
            xml, errors, extra = await _validate_local(user_input)
            placeholders.update(extra)
            if not errors:
                self._title = user_input[CONF_NAME]
                self._data = {
                    CONF_HOST: user_input[CONF_HOST].strip(),
                    CONF_PORT: user_input[CONF_PORT],
                    CONF_DAQ_XML: xml,
                    CONF_MODEL: DEFAULT_MODEL,
                }
                return await self.async_step_cloud()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_local_schema({}, True), user_input),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_cloud(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_USE_CLOUD]:
                return self.async_create_entry(title=self._title, data={**self._data, CONF_USE_CLOUD: False})
            if not user_input.get(CONF_EMAIL) or not user_input.get(CONF_PASSWORD):
                errors["base"] = "credentials_required"
            else:
                installations, error = await _cloud_login(
                    self.hass, user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
                if error:
                    errors["base"] = error
                else:
                    self._data.update(
                        {
                            CONF_USE_CLOUD: True,
                            CONF_EMAIL: user_input[CONF_EMAIL],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        }
                    )
                    self._installations = installations
                    if len(installations) == 1:
                        return self._create_with_installation(installations[0])
                    return await self.async_step_installation()

        return self.async_show_form(
            step_id="cloud", data_schema=_cloud_schema(user_input or {}), errors=errors
        )

    async def async_step_installation(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            chosen = next(
                (i for i in self._installations if str(i.get("id")) == user_input[CONF_INSTALLATION_ID]),
                None,
            )
            if chosen is not None:
                return self._create_with_installation(chosen)

        options = [
            SelectOptionDict(value=str(i.get("id")), label=str(i.get("name") or i.get("id")))
            for i in self._installations
        ]
        return self.async_show_form(
            step_id="installation",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INSTALLATION_ID): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                    )
                }
            ),
        )

    def _create_with_installation(self, installation: dict[str, Any]) -> ConfigFlowResult:
        self._data[CONF_INSTALLATION_ID] = str(installation.get("id"))
        self._data[CONF_INSTALLATION_NAME] = str(installation.get("name") or installation.get("id"))
        return self.async_create_entry(title=self._title, data=self._data)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change host or re-import the DAQ template (e.g. after a firmware update)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"received": "?", "expected": "?", "error_detail": ""}
        if user_input is not None:
            xml, errors, extra = await _validate_local(user_input)
            placeholders.update(extra)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: user_input[CONF_HOST].strip(),
                        CONF_PORT: user_input[CONF_PORT],
                        CONF_DAQ_XML: xml,
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_local_schema(user_input or entry.data, False),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Cloud credentials were rejected."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            _, error = await _cloud_login(self.hass, user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL, default=entry.data.get(CONF_EMAIL, "")): str,
                    vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                }
            ),
            errors=errors,
        )


def _number(minimum: float, maximum: float, step: float, unit: str) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=NumberSelectorMode.BOX)
    )


class HargassnerHKOptionsFlow(OptionsFlow):
    """Update intervals and fuel parameters."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            if user_input.get(CONF_POWER_CHANNEL) == NO_CHANNEL:
                user_input[CONF_POWER_CHANNEL] = ""
            return self.async_create_entry(data=user_input)

        entry = self.config_entry
        opts = entry.options
        try:
            channel_names = [ch.name for ch in parse_daq_xml(entry.data[CONF_DAQ_XML]).analog]
        except DaqFormatError:
            channel_names = []
        default_power = opts.get(CONF_POWER_CHANNEL, DEFAULT_POWER_CHANNEL) or NO_CHANNEL
        if default_power not in channel_names:
            default_power = NO_CHANNEL

        schema: dict[Any, Any] = {
            vol.Required(
                CONF_UPDATE_INTERVAL, default=opts.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            ): _number(2, 300, 1, "s"),
        }
        if entry.data.get(CONF_USE_CLOUD):
            schema[
                vol.Required(CONF_CLOUD_INTERVAL, default=opts.get(CONF_CLOUD_INTERVAL, DEFAULT_CLOUD_INTERVAL))
            ] = _number(30, 3600, 10, "s")
        schema.update(
            {
                vol.Required(CONF_POWER_CHANNEL, default=default_power): SelectSelector(
                    SelectSelectorConfig(options=[NO_CHANNEL, *channel_names], mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required(
                    CONF_NOMINAL_POWER, default=opts.get(CONF_NOMINAL_POWER, DEFAULT_NOMINAL_POWER)
                ): _number(5, 500, 0.5, "kW"),
                vol.Required(
                    CONF_CALORIFIC_VALUE, default=opts.get(CONF_CALORIFIC_VALUE, DEFAULT_CALORIFIC_VALUE)
                ): _number(1, 6, 0.05, "kWh/kg"),
                vol.Required(
                    CONF_BULK_DENSITY, default=opts.get(CONF_BULK_DENSITY, DEFAULT_BULK_DENSITY)
                ): _number(100, 450, 1, "kg/SRM"),
                vol.Required(
                    CONF_EFFICIENCY, default=opts.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)
                ): _number(50, 100, 0.5, "%"),
            }
        )
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
