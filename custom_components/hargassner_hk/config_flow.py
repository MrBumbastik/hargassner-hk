"""Config flow for Hargassner HK."""
from __future__ import annotations

from collections.abc import Mapping
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
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
    CONF_ALLOW_CLOUD_WRITE,
    DEFAULT_ALLOW_CLOUD_WRITE,
    CONF_BULK_DENSITY,
    CONF_CALORIFIC_VALUE,
    CONF_CLOUD_INTERVAL,
    CONF_DAQ_XML,
    CONF_STREAM_EXTRAS,
    CONF_TEMPLATE_SOURCE,
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
from .daq import (
    DaqFormatError,
    decode_frame,
    extract_daq_xml,
    fit_to_stream,
    parse_daq_xml,
    split_pm_line,
    with_stream_extras,
)
from .entity import remove_cloud_entities
from .templates import TEMPLATE_USER, detect_template, is_builtin, load_builtin_templates, plausible
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
    # Optional without default: empty (or omitted) means "detect from the shipped templates".
    # Prefill via suggested values only, so clearing the field really clears it.
    schema[vol.Optional(CONF_DAQ_XML)] = TextSelector(
        TextSelectorConfig(multiline=True)
    )
    return vol.Schema(schema)


def _cloud_schema() -> vol.Schema:
    # No separate on/off switch: credentials entered = cloud on, both empty = cloud off.
    # (A switch defaulting to off silently discarded entered credentials.)
    return vol.Schema(
        {
            vol.Optional(CONF_EMAIL): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
            vol.Optional(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        }
    )


def _credentials(user_input: dict[str, Any]) -> tuple[str, str]:
    return (user_input.get(CONF_EMAIL) or "").strip(), user_input.get(CONF_PASSWORD) or ""


async def _validate_local(
    hass: Any, user_input: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    """Check the boiler connection and find a template that fits its stream.

    Without a pasted template, the templates shipped with the integration are tried.
    Returns (entry data for host/port/template, errors, description placeholders).
    """
    raw = (user_input.get(CONF_DAQ_XML) or "").strip()
    fmt = None
    if raw:
        try:
            xml = extract_daq_xml(raw)
            fmt = parse_daq_xml(xml)
        except DaqFormatError as err:
            _LOGGER.debug("Invalid DAQ template: %s", err)
            return {}, {CONF_DAQ_XML: "invalid_daq"}, {"error_detail": str(err)}

    try:
        line = await read_pm_line(user_input[CONF_HOST], user_input[CONF_PORT])
    except (OSError, TimeoutError, ConnectionError, ValueError) as err:
        # ValueError: garbage without newline beyond the stream reader limit
        _LOGGER.debug("Cannot read pm line: %s", err)
        return {}, {"base": "cannot_connect"}, {}
    received = len(split_pm_line(line) or [])

    if fmt is None:
        templates = await hass.async_add_executor_job(load_builtin_templates)
        detection = detect_template(templates, received)
        if detection is None:
            return {}, {CONF_DAQ_XML: "template_required"}, {"received": str(received)}
        xml, fmt, extras, source = detection.xml, detection.fmt, detection.extras, detection.source
    else:
        extras, source = fit_to_stream(fmt, received), TEMPLATE_USER

    frame = None if extras is None else decode_frame(with_stream_extras(fmt, extras), line, dt_util.utcnow())
    if frame is None:
        return {}, {CONF_DAQ_XML: "template_mismatch"}, {
            "received": str(received),
            "expected": str(fmt.expected_length),
        }
    if source != TEMPLATE_USER and not plausible(frame):
        _LOGGER.warning("Shipped template %s fits by length but gives implausible values", source)
        return {}, {CONF_DAQ_XML: "template_required"}, {"received": str(received)}
    if extras:
        _LOGGER.info("Stream has %s values more than the template, applying known correction", len(extras))
    return {
        CONF_HOST: user_input[CONF_HOST],
        CONF_PORT: user_input[CONF_PORT],
        CONF_DAQ_XML: xml,
        CONF_STREAM_EXTRAS: list(extras),
        CONF_TEMPLATE_SOURCE: source,
    }, {}, {}


def model_info(installation: dict[str, Any]) -> tuple[str | None, float | None]:
    """Model name and nominal power from the cloud, e.g. 'Eco-HK 50' -> ('Eco-HK 50', 50.0)."""
    devices = installation.get("devices") or []
    model = next((d.get("type") for d in devices if isinstance(d, dict) and isinstance(d.get("type"), str)), None)
    if not model:
        return None, None
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:kW)?\s*$", model, re.IGNORECASE)
    power = float(match.group(1).replace(",", ".")) if match else None
    return model, power if power and 5 <= power <= 500 else None


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
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(user_input[CONF_HOST].lower())
            self._abort_if_unique_id_configured()
            local, errors, extra = await _validate_local(self.hass, user_input)
            placeholders.update(extra)
            if not errors:
                self._title = user_input[CONF_NAME]
                self._data = {**local, CONF_MODEL: DEFAULT_MODEL}
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
            email, password = _credentials(user_input)
            if not email and not password:
                return self.async_create_entry(title=self._title, data={**self._data, CONF_USE_CLOUD: False})
            errors = await self._cloud_credentials(email, password)
            if not errors:
                return await self._after_login()

        return self.async_show_form(
            step_id="cloud",
            data_schema=self.add_suggested_values_to_schema(_cloud_schema(), {CONF_EMAIL: (user_input or {}).get(CONF_EMAIL, "")}),
            errors=errors,
        )

    async def _after_login(self) -> ConfigFlowResult:
        if len(self._installations) == 1:
            return self._create_with_installation(self._installations[0])
        return await self.async_step_installation()

    async def _cloud_credentials(self, email: str, password: str) -> dict[str, str]:
        """Log in and remember credentials + installations; returns form errors."""
        if not email or not password:
            return {"base": "credentials_required"}
        installations, error = await _cloud_login(self.hass, email, password)
        if error:
            return {"base": error}
        self._data.update({CONF_USE_CLOUD: True, CONF_EMAIL: email, CONF_PASSWORD: password})
        self._installations = installations
        return {}

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
        model, power = model_info(installation)
        options: dict[str, Any] = {}
        if model:
            self._data[CONF_MODEL] = model
        if power:
            options[CONF_NOMINAL_POWER] = power
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            if entry.data.get(CONF_INSTALLATION_ID) not in (None, self._data[CONF_INSTALLATION_ID]):
                remove_cloud_entities(self.hass, entry)  # other installation: old widgets are gone
            new_options = dict(entry.options)
            # Replace the power only if it is the generic default or came from the previous model
            _, previous = model_info({"devices": [{"type": entry.data.get(CONF_MODEL, "")}]})
            current = float(entry.options.get(CONF_NOMINAL_POWER, DEFAULT_NOMINAL_POWER))
            if power and current in (DEFAULT_NOMINAL_POWER, previous):
                new_options[CONF_NOMINAL_POWER] = power
            # One update + one reload (a separate options update would reload twice)
            return self.async_update_reload_and_abort(entry, data_updates=self._data, options=new_options)
        return self.async_create_entry(title=self._title, data=self._data, options=options)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose what to change: local connection/template or cloud login."""
        return self.async_show_menu(step_id="reconfigure", menu_options=["reconfigure_local", "reconfigure_cloud"])

    async def async_step_reconfigure_cloud(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Add, change or remove the cloud login after setup."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            email, password = _credentials(user_input)
            if not email and not password:
                if not entry.data.get(CONF_USE_CLOUD):
                    return self.async_abort(reason="reconfigure_successful")  # nothing to remove
                remove_cloud_entities(self.hass, entry)
                cloud_keys = (CONF_EMAIL, CONF_PASSWORD, CONF_INSTALLATION_ID, CONF_INSTALLATION_NAME)
                return self.async_update_reload_and_abort(
                    entry,
                    data={k: v for k, v in entry.data.items() if k not in cloud_keys} | {CONF_USE_CLOUD: False},
                )
            self._data = {}
            errors = await self._cloud_credentials(email, password)
            if not errors:
                return await self._after_login()
        return self.async_show_form(
            step_id="reconfigure_cloud",
            data_schema=self.add_suggested_values_to_schema(
                _cloud_schema(), {CONF_EMAIL: (user_input or {}).get(CONF_EMAIL) or entry.data.get(CONF_EMAIL, "")}
            ),
            errors=errors,
        )

    async def async_step_reconfigure_local(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change host or re-import the DAQ template (e.g. after a firmware update)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"received": "?", "expected": "?", "error_detail": ""}
        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()
            new_id = user_input[CONF_HOST].lower()
            if any(e.unique_id == new_id and e.entry_id != entry.entry_id for e in self._async_current_entries()):
                return self.async_abort(reason="already_configured")
            local, errors, extra = await _validate_local(self.hass, user_input)
            placeholders.update(extra)
            if not errors:
                return self.async_update_reload_and_abort(entry, unique_id=new_id, data_updates=local)
        return self.async_show_form(
            step_id="reconfigure_local",
            data_schema=self.add_suggested_values_to_schema(
                _local_schema(user_input or entry.data, False),
                # A shipped template is not shown: leaving the field empty keeps auto-detection
                user_input or {CONF_DAQ_XML: "" if is_builtin(entry.data) else entry.data.get(CONF_DAQ_XML, "")},
            ),
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
            email, password = _credentials(user_input)
            user_input = {CONF_EMAIL: email, CONF_PASSWORD: password}
            _, error = await _cloud_login(self.hass, email, password)
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
            schema[
                vol.Required(CONF_ALLOW_CLOUD_WRITE, default=opts.get(CONF_ALLOW_CLOUD_WRITE, DEFAULT_ALLOW_CLOUD_WRITE))
            ] = BooleanSelector()
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
