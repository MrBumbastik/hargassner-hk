"""Climate entities for heating circuits (via cloud)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HargassnerHKConfigEntry
from .coordinator import CloudCoordinator, CloudData
from .entity import CloudEntity, add_cloud_entities

PARALLEL_UPDATES = 1

MODE_OFF = "MODE_OFF"
MODE_AUTOMATIC = "MODE_AUTOMATIC"
MODE_HEATING = "MODE_HEATING"
SETPOINT = "room_temperature_heating"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HargassnerHKConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    def _cloud(cloud: CloudCoordinator, data: CloudData) -> list[ClimateEntity]:
        return [
            CircuitClimate(cloud, widget_id)
            for widget_id, widget in data.widgets.items()
            if widget["type"].startswith("HEATING_CIRCUIT") and SETPOINT in widget["parameters"]
        ]

    add_cloud_entities(entry, async_add_entities, _cloud)


class CircuitClimate(CloudEntity, ClimateEntity):
    """Room setpoint and on/off of a heating circuit."""

    _attr_name = None  # use the circuit device name
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator: CloudCoordinator, widget_id: str) -> None:
        super().__init__(coordinator, widget_id, "climate")

    def _mode_param(self) -> dict[str, Any] | None:
        return self.parameter("mode")

    @property
    def supported_features(self) -> ClimateEntityFeature:
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if self._mode_param():
            features |= ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        return features

    @property
    def hvac_modes(self) -> list[HVACMode]:
        if self._mode_param():
            return [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
        return [HVACMode.AUTO]

    @property
    def hvac_mode(self) -> HVACMode:
        param = self._mode_param()
        value = param.get("value") if param else None
        if value == MODE_OFF:
            return HVACMode.OFF
        if value == MODE_HEATING:
            return HVACMode.HEAT
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction | None:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        pump = self.widget_value("pump_active")
        if pump is None:
            return None
        return HVACAction.HEATING if pump else HVACAction.IDLE

    def _float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def current_temperature(self) -> float | None:
        return self._float(self.widget_value("room_temperature_current"))

    @property
    def target_temperature(self) -> float | None:
        param = self.parameter(SETPOINT)
        return self._float(param.get("value")) if param else None

    @property
    def min_temp(self) -> float:
        param = self.parameter(SETPOINT) or {}
        return self._float(param.get("min")) or 14.0

    @property
    def max_temp(self) -> float:
        param = self.parameter(SETPOINT) or {}
        return self._float(param.get("max")) or 26.0

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        param = self.parameter(SETPOINT)
        if temperature is not None and param and param.get("resource"):
            await self.coordinator.async_set_value(param["resource"], temperature)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        param = self._mode_param()
        if not param or not param.get("resource"):
            return
        value = {HVACMode.OFF: MODE_OFF, HVACMode.HEAT: MODE_HEATING}.get(hvac_mode, MODE_AUTOMATIC)
        options = param.get("options") or []
        if options and value not in options:
            value = MODE_AUTOMATIC
        await self.coordinator.async_set_value(param["resource"], value)
