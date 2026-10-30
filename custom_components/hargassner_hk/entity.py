"""Base entities."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HargassnerHKConfigEntry
from .const import CONF_MODEL, DEFAULT_MODEL, DOMAIN, MANUFACTURER
from .coordinator import CloudCoordinator, CloudData, LocalCoordinator


def boiler_device(entry: HargassnerHKConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=entry.data.get(CONF_MODEL, DEFAULT_MODEL),
    )


class LocalEntity(CoordinatorEntity[LocalCoordinator]):
    """Entity fed by the local telnet stream."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LocalCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = boiler_device(entry)


class CloudEntity(CoordinatorEntity[CloudCoordinator]):
    """Entity backed by a cloud widget parameter."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CloudCoordinator, widget_id: str, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._widget_id = widget_id
        self._attr_unique_id = f"{entry.entry_id}_cloud_{widget_id}_{key}"
        widget = coordinator.data.widgets[widget_id]
        if widget["type"].startswith("HEATER"):
            self._attr_device_info = boiler_device(entry)
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry.entry_id}_{widget_id}")},
                name=widget["name"],
                manufacturer=MANUFACTURER,
                model=widget["type"].replace("_", " ").title(),
                via_device=(DOMAIN, entry.entry_id),
            )

    @property
    def widget(self) -> dict[str, Any] | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.widgets.get(self._widget_id)

    def parameter(self, key: str) -> dict[str, Any] | None:
        widget = self.widget
        return widget["parameters"].get(key) if widget else None

    def widget_value(self, key: str) -> Any:
        widget = self.widget
        return widget["values"].get(key) if widget else None

    @property
    def available(self) -> bool:
        return super().available and self.widget is not None and self.coordinator.data.online


def add_cloud_entities(
    entry: HargassnerHKConfigEntry,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[CloudCoordinator, CloudData], Iterable[Entity]],
) -> None:
    """Add cloud entities now, or as soon as the cloud delivers data."""
    cloud = entry.runtime_data.cloud
    if cloud is None:
        return
    added: set[str] = set()

    @callback
    def _add() -> None:
        if cloud.data is None:
            return
        new = [e for e in factory(cloud, cloud.data) if e.unique_id not in added]
        if new:
            added.update(e.unique_id for e in new if e.unique_id)
            async_add_entities(new)

    _add()
    entry.async_on_unload(cloud.async_add_listener(_add))


@callback
def remove_cloud_entities(hass: Any, entry: HargassnerHKConfigEntry) -> None:
    """Delete cloud entities and heating circuit devices (cloud removed or other installation)."""
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.unique_id.startswith(f"{entry.entry_id}_cloud_"):
            ent_reg.async_remove(ent.entity_id)
    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if all(ident != (DOMAIN, entry.entry_id) for ident in device.identifiers):
            dev_reg.async_remove_device(device.id)
