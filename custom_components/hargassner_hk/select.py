"""Selects for cloud option parameters (circuit mode etc.)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HargassnerHKConfigEntry
from .coordinator import CloudCoordinator, CloudData
from .entity import CloudEntity, add_cloud_entities

PARALLEL_UPDATES = 1

# Parameter key -> translation key. Options are translated as lowercased API values.
KNOWN_SELECTS = {
    "program": "heater_program",
    "mode": "circuit_mode",
    "pool_heating": "pool_heating",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HargassnerHKConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    def _cloud(cloud: CloudCoordinator, data: CloudData) -> list[SelectEntity]:
        return [
            CloudSelect(cloud, widget_id, key)
            for widget_id, widget in data.widgets.items()
            for key, param in widget["parameters"].items()
            if param.get("resource") and isinstance(param.get("options"), list) and param["options"]
        ]

    add_cloud_entities(entry, async_add_entities, _cloud)


class CloudSelect(CloudEntity, SelectEntity):
    """An option parameter of a cloud widget."""

    def __init__(self, coordinator: CloudCoordinator, widget_id: str, key: str) -> None:
        super().__init__(coordinator, widget_id, key)
        self._key = key
        if translation_key := KNOWN_SELECTS.get(key):
            self._attr_translation_key = translation_key
        else:
            self._attr_name = key.replace("_", " ").capitalize()
            self._attr_entity_registry_enabled_default = False

    def _api_options(self) -> list[str]:
        param = self.parameter(self._key) or {}
        return [str(o) for o in param.get("options") or []]

    @property
    def options(self) -> list[str]:
        return [o.lower() for o in self._api_options()]

    @property
    def current_option(self) -> str | None:
        param = self.parameter(self._key)
        value = param.get("value") if param else None
        return str(value).lower() if value is not None else None

    async def async_select_option(self, option: str) -> None:
        api_value = next((o for o in self._api_options() if o.lower() == option), option)
        param = self.parameter(self._key)
        if param and param.get("resource"):
            await self.coordinator.async_set_value(param["resource"], api_value)
