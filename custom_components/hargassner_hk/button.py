"""Buttons for cloud widget actions (force charging, one-time circulation)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HargassnerHKConfigEntry
from .coordinator import CloudCoordinator, CloudData
from .entity import CloudEntity, add_cloud_entities

PARALLEL_UPDATES = 1

# (widget type prefix, action) -> (translation key, icon)
KNOWN_ACTIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("BUFFER", "force_charging"): ("buffer_force_charging", "mdi:battery-charging-high"),
    ("BOILER", "force_charging"): ("dhw_force_charging", "mdi:water-boiler"),
    ("BOILER", "one_time_circulation"): ("one_time_circulation", "mdi:sync"),
}


def _meta(widget_type: str, action: str) -> tuple[str, str] | None:
    return next((m for (prefix, a), m in KNOWN_ACTIONS.items() if a == action and widget_type.startswith(prefix)), None)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HargassnerHKConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    def _cloud(cloud: CloudCoordinator, data: CloudData) -> list[ButtonEntity]:
        return [
            CloudActionButton(cloud, widget_id, action)
            for widget_id, widget in data.widgets.items()
            for action in widget["actions"]
        ]

    add_cloud_entities(entry, async_add_entities, _cloud)


class CloudActionButton(CloudEntity, ButtonEntity):
    """Triggers an action of a cloud widget."""

    def __init__(self, coordinator: CloudCoordinator, widget_id: str, action: str) -> None:
        super().__init__(coordinator, widget_id, f"action_{action}")
        self._action = action
        if meta := _meta(coordinator.data.widgets[widget_id]["type"], action):
            self._attr_translation_key, self._attr_icon = meta
        else:
            self._attr_name = action.replace("_", " ").capitalize()
            self._attr_entity_registry_enabled_default = False

    async def async_press(self) -> None:
        widget = self.widget
        if widget and (resource := widget["actions"].get(self._action)):
            await self.coordinator.async_post_action(resource)
