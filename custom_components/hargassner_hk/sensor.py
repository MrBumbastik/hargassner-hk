"""Sensors: analog channels, boiler state, faults, heat and fuel figures."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HargassnerHKConfigEntry
from .channels import (
    BOILER_STATE_OPTIONS,
    BOILER_STATE_OTHER,
    BOILER_STATES,
    analog_meta,
    error_text,
    is_wood_chip,
    unit_meta,
    unit_scale,
)
from .const import CHANNEL_ERROR, CHANNEL_STATE, UNIT_SRM
from .coordinator import LocalCoordinator
from .daq import AnalogChannel, slugify
from .entity import LocalEntity
from .fuel import FuelTracker

PARALLEL_UPDATES = 0
SPECIAL_CHANNELS = {slugify(CHANNEL_STATE), slugify(CHANNEL_ERROR)}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HargassnerHKConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = entry.runtime_data
    local = data.local
    wood_chip = is_wood_chip({ch.key for ch in data.fmt.digital})
    entities: list[SensorEntity] = [
        AnalogSensor(local, ch, wood_chip) for ch in data.fmt.analog if ch.key not in SPECIAL_CHANNELS
    ]

    if state := data.fmt.analog_by_name(CHANNEL_STATE):
        entities.append(BoilerStateSensor(local, state.key))
    if error := data.fmt.analog_by_name(CHANNEL_ERROR):
        entities.append(ErrorSensor(local, error.key))

    if local.power_key:
        entities.extend(FuelSensor(local, desc) for desc in FUEL_SENSORS)

    if local.runtime is not None:
        for counter in local.runtime.counters:
            entities.append(RuntimeSensor(local, counter.key))
            if counter.has_boiler_counter:
                entities.append(CounterSensor(local, counter.key))

    entities.append(ConnectionInfoSensor(local))
    async_add_entities(entities)


class AnalogSensor(LocalEntity, SensorEntity):
    """One analog value of the pm line."""

    def __init__(self, coordinator: LocalCoordinator, channel: AnalogChannel, wood_chip: bool = False) -> None:
        super().__init__(coordinator, f"a_{channel.key}")
        self._key = channel.key
        self._scale = unit_scale(channel.unit)
        meta = analog_meta(channel.key, channel.unit, wood_chip)
        device_class, unit, state_class = unit_meta(channel.unit)
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._attr_entity_registry_enabled_default = meta.enabled
        if meta.icon:
            self._attr_icon = meta.icon
        if meta.translation_key:
            self._attr_translation_key = meta.translation_key
            self._attr_translation_placeholders = meta.placeholders or {}
        else:
            self._attr_name = channel.name
        if device_class == SensorDeviceClass.DURATION and meta.translation_key:
            self._attr_suggested_unit_of_measurement = UnitOfTime.HOURS  # e.g. feed screw counter (min)
        if device_class is None and unit is None:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> float | str | None:
        value = self.coordinator.data.analog.get(self._key)
        if isinstance(value, float):
            value *= self._scale
            return int(value) if value.is_integer() else value
        if self.state_class is not None or self.native_unit_of_measurement:
            return None  # a non-numeric value would break the statistics
        return value


class BoilerStateSensor(LocalEntity, SensorEntity):
    """Boiler state (ZK) as enum."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = BOILER_STATE_OPTIONS
    _attr_translation_key = "boiler_state"

    def __init__(self, coordinator: LocalCoordinator, key: str) -> None:
        super().__init__(coordinator, "boiler_state")
        self._key = key

    def _code(self) -> int | None:
        value = self.coordinator.data.analog.get(self._key)
        return int(value) if isinstance(value, float) else None

    @property
    def native_value(self) -> str | None:
        code = self._code()
        if code is None:
            return None
        return BOILER_STATES.get(code, BOILER_STATE_OTHER)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"code": self._code()}


class ErrorSensor(LocalEntity, SensorEntity):
    """Current fault (Störungs Nr) as text."""

    _attr_translation_key = "fault_message"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: LocalCoordinator, key: str) -> None:
        super().__init__(coordinator, "fault_message")
        self._key = key

    def _code(self) -> int | None:
        value = self.coordinator.data.analog.get(self._key)
        return int(value) if isinstance(value, float) else None

    @property
    def native_value(self) -> str | None:
        code = self._code()
        if code is None:
            return None
        return error_text(code, self.hass.config.language)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"code": self._code()}

    @property
    def icon(self) -> str:
        return "mdi:alert-circle" if self._code() else "mdi:check-circle-outline"


@dataclass(frozen=True, kw_only=True)
class FuelSensorDescription(SensorEntityDescription):
    """Describes a figure computed by the fuel tracker."""

    value_fn: Callable[[FuelTracker], float | None]


def _today() -> date:
    return dt_util.now().date()


FUEL_SENSORS: tuple[FuelSensorDescription, ...] = (
    FuelSensorDescription(
        key="heat_energy",
        translation_key="heat_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda f: f.heat_kwh,
    ),
    FuelSensorDescription(
        key="fuel_consumed",
        translation_key="fuel_consumed",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=1,
        icon="mdi:pine-tree",
        value_fn=lambda f: f.fuel_kg,
    ),
    FuelSensorDescription(
        key="fuel_consumed_srm",
        translation_key="fuel_consumed_srm",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UNIT_SRM,
        suggested_display_precision=2,
        icon="mdi:pine-tree",
        value_fn=lambda f: f.fuel_srm,
    ),
    FuelSensorDescription(
        key="fuel_today",
        translation_key="fuel_today",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=1,
        icon="mdi:calendar-today",
        value_fn=lambda f: f.consumption_today_kg(_today()),
    ),
    FuelSensorDescription(
        key="fuel_daily_average",
        translation_key="fuel_daily_average",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="kg/d",
        suggested_display_precision=1,
        icon="mdi:chart-line",
        value_fn=lambda f: f.average_daily_kg(_today()),
    ),
    FuelSensorDescription(
        key="storage_kg",
        translation_key="storage_kg",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=0,
        icon="mdi:warehouse",
        value_fn=lambda f: f.storage_kg,
    ),
    FuelSensorDescription(
        key="storage_srm",
        translation_key="storage_srm",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UNIT_SRM,
        suggested_display_precision=1,
        icon="mdi:warehouse",
        value_fn=lambda f: f.storage_srm,
    ),
    FuelSensorDescription(
        key="days_remaining",
        translation_key="days_remaining",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.DAYS,
        suggested_display_precision=0,
        icon="mdi:calendar-end",
        value_fn=lambda f: f.days_remaining(_today()),
    ),
)


class FuelSensor(LocalEntity, SensorEntity):
    """Heat / fuel figure computed from the burner output."""

    entity_description: FuelSensorDescription

    def __init__(self, coordinator: LocalCoordinator, description: FuelSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        # Totals stay valid while the stream is down.
        return True

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.fuel)


class ConnectionInfoSensor(LocalEntity, SensorEntity):
    """Diagnostic: number of frames received / rejected."""

    _attr_translation_key = "frames_received"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: LocalCoordinator) -> None:
        super().__init__(coordinator, "frames_received")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> int:
        return self.coordinator.client.frames_received

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        client = self.coordinator.client
        return {
            "frames_rejected": client.frames_rejected,
            "last_rejected_length": client.last_rejected_length,
            "expected_length": client.fmt.expected_length,
            "last_error": client.last_error,
        }


class RuntimeSensor(LocalEntity, SensorEntity):
    """Operating hours counted since installation (basis for hours per day/week/month)."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: LocalCoordinator, key: str) -> None:
        super().__init__(coordinator, f"hours_{key}")
        self._key = key
        self._attr_translation_key = f"hours_{key}"

    @property
    def available(self) -> bool:
        return True  # totals stay valid while the stream is down

    @property
    def native_value(self) -> float:
        return round(self.coordinator.runtime.hours(self._key), 3)


class CounterSensor(LocalEntity, SensorEntity):
    """Boiler-style counter: start value from the boiler + counted hours (display only)."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:counter"
    # No state_class on purpose: setting the start value would otherwise show up as
    # thousands of hours on a single day in the statistics.

    def __init__(self, coordinator: LocalCoordinator, key: str) -> None:
        super().__init__(coordinator, f"counter_{key}")
        self._key = key
        self._attr_translation_key = f"counter_{key}"

    @property
    def available(self) -> bool:
        return self.coordinator.runtime.counter_hours(self._key) is not None

    @property
    def native_value(self) -> float | None:
        value = self.coordinator.runtime.counter_hours(self._key)
        return None if value is None else round(value, 1)
