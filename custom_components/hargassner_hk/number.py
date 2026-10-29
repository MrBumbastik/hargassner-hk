"""Numbers: wood chip storage level (local) and writable cloud parameters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HargassnerHKConfigEntry
from .const import UNIT_SRM
from .coordinator import CloudCoordinator, CloudData, LocalCoordinator
from .entity import CloudEntity, LocalEntity, add_cloud_entities

PARALLEL_UPDATES = 1


@dataclass(frozen=True)
class CloudNumberMeta:
    translation_key: str
    temperature: bool = True
    mode: NumberMode = NumberMode.BOX
    icon: str | None = None


KNOWN_NUMBERS: dict[str, CloudNumberMeta] = {
    "room_temperature_heating": CloudNumberMeta("room_temperature_day"),
    "room_temperature_reduction": CloudNumberMeta("room_temperature_night"),
    "deactivation_limit_heating": CloudNumberMeta("deactivation_limit_heating"),
    "deactivation_limit_reduction_day": CloudNumberMeta("deactivation_limit_reduction_day"),
    "deactivation_limit_reduction_night": CloudNumberMeta("deactivation_limit_reduction_night"),
    "steepness": CloudNumberMeta("heating_curve_steepness", temperature=False, mode=NumberMode.SLIDER, icon="mdi:slope-uphill"),
    # Floor heating circuits use their own key for the curve
    "steepness_floor": CloudNumberMeta("heating_curve_steepness", temperature=False, mode=NumberMode.SLIDER, icon="mdi:slope-uphill"),
    "room_temperature_correction": CloudNumberMeta("room_temperature_correction"),
    "boiler_temperature_target": CloudNumberMeta("dhw_temperature_target", icon="mdi:water-boiler"),
}


def _is_number_param(param: dict[str, Any]) -> bool:
    value = param.get("value")
    return (
        bool(param.get("resource"))
        and not param.get("options")
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HargassnerHKConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    local = entry.runtime_data.local
    if local.power_key:
        async_add_entities([StorageNumber(local)])

    def _cloud(cloud: CloudCoordinator, data: CloudData) -> list[NumberEntity]:
        return [
            CloudNumber(cloud, widget_id, key)
            for widget_id, widget in data.widgets.items()
            for key, param in widget["parameters"].items()
            if _is_number_param(param)
        ]

    add_cloud_entities(entry, async_add_entities, _cloud)


class StorageNumber(LocalEntity, NumberEntity):
    """Wood chip storage level in SRM; set after a delivery, reduced by consumption."""

    _attr_translation_key = "storage_level"
    _attr_icon = "mdi:warehouse"
    _attr_native_unit_of_measurement = UNIT_SRM
    _attr_native_min_value = 0
    _attr_native_max_value = 1000
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: LocalCoordinator) -> None:
        super().__init__(coordinator, "storage_level")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float | None:
        srm = self.coordinator.fuel.storage_srm
        return None if srm is None else round(srm, 2)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.fuel.set_storage_srm(value)
        await self.coordinator.async_save_fuel_now()
        self.async_write_ha_state()


class CloudNumber(CloudEntity, NumberEntity):
    """A numeric cloud parameter."""

    def __init__(self, coordinator: CloudCoordinator, widget_id: str, key: str) -> None:
        super().__init__(coordinator, widget_id, key)
        self._key = key
        widget = coordinator.data.widgets[widget_id]
        meta = KNOWN_NUMBERS.get(key)
        temperature = meta.temperature if meta else ("temperature" in key or "limit" in key)
        if meta:
            self._attr_translation_key = meta.translation_key
            self._attr_mode = meta.mode
            if meta.icon:
                self._attr_icon = meta.icon
        else:
            self._attr_name = key.replace("_", " ").capitalize()
            self._attr_entity_registry_enabled_default = False
            self._attr_mode = NumberMode.BOX
        if temperature:
            self._attr_device_class = NumberDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif unit := widget["parameters"][key].get("unit"):
            self._attr_native_unit_of_measurement = str(unit)

    def _param_float(self, attr: str, default: float) -> float:
        param = self.parameter(self._key) or {}
        try:
            return float(param.get(attr, default))
        except (TypeError, ValueError):
            return default

    @property
    def native_min_value(self) -> float:
        return self._param_float("min", -100.0)

    @property
    def native_max_value(self) -> float:
        return self._param_float("max", 100.0)

    @property
    def native_step(self) -> float:
        return self._param_float("step", 0.5)

    @property
    def native_value(self) -> float | None:
        param = self.parameter(self._key)
        value = param.get("value") if param else None
        return float(value) if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        param = self.parameter(self._key)
        if param and param.get("resource"):
            await self.coordinator.async_set_value(param["resource"], value)
