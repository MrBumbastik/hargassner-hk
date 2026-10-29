"""Binary sensors: digital channels, connection, burner and fault state."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HargassnerHKConfigEntry
from .channels import BOILER_STATES, BURNING_STATES, digital_meta
from .const import CHANNEL_ERROR, CHANNEL_STATE
from .coordinator import CloudCoordinator, CloudData, LocalCoordinator
from .daq import DigitalChannel
from .entity import CloudEntity, LocalEntity, add_cloud_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HargassnerHKConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = entry.runtime_data
    local = data.local
    entities: list[BinarySensorEntity] = [DigitalSensor(local, ch) for ch in data.fmt.digital]
    entities.append(ConnectionSensor(local))
    if state := data.fmt.analog_by_name(CHANNEL_STATE):
        entities.append(BurningSensor(local, state.key))
    if error := data.fmt.analog_by_name(CHANNEL_ERROR):
        entities.append(FaultActiveSensor(local, error.key))
    async_add_entities(entities)

    def _cloud(cloud: CloudCoordinator, cloud_data: CloudData) -> list[BinarySensorEntity]:
        heater = next((wid for wid, w in cloud_data.widgets.items() if w["type"].startswith("HEATER")), None)
        return [CloudOnlineSensor(cloud, heater)] if heater else []

    add_cloud_entities(entry, async_add_entities, _cloud)


class DigitalSensor(LocalEntity, BinarySensorEntity):
    """One bit of the pm line."""

    def __init__(self, coordinator: LocalCoordinator, channel: DigitalChannel) -> None:
        super().__init__(coordinator, f"d_{channel.key}")
        self._key = channel.key
        meta = digital_meta(channel.key)
        self._attr_device_class = meta.device_class
        self._attr_entity_registry_enabled_default = meta.enabled
        if meta.icon:
            self._attr_icon = meta.icon
        if meta.translation_key:
            self._attr_translation_key = meta.translation_key
            self._attr_translation_placeholders = meta.placeholders or {}
        else:
            self._attr_name = channel.name
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.digital.get(self._key)


class ConnectionSensor(LocalEntity, BinarySensorEntity):
    """Is the local stream delivering valid frames?"""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "local_connection"

    def __init__(self, coordinator: LocalCoordinator) -> None:
        super().__init__(coordinator, "local_connection")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class BurningSensor(LocalEntity, BinarySensorEntity):
    """Is the burner firing (ignition / full firing)?"""

    _attr_device_class = BinarySensorDeviceClass.HEAT
    _attr_translation_key = "burning"

    def __init__(self, coordinator: LocalCoordinator, key: str) -> None:
        super().__init__(coordinator, "burning")
        self._key = key

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.data.analog.get(self._key)
        if not isinstance(value, float):
            return None
        return BOILER_STATES.get(int(value)) in BURNING_STATES


class FaultActiveSensor(LocalEntity, BinarySensorEntity):
    """A fault code is pending (Störungs Nr != 0)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "fault_active"

    def __init__(self, coordinator: LocalCoordinator, key: str) -> None:
        super().__init__(coordinator, "fault_active")
        self._key = key

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.data.analog.get(self._key)
        return None if not isinstance(value, float) else value != 0


class CloudOnlineSensor(CloudEntity, BinarySensorEntity):
    """Does the cloud see the boiler online?"""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "cloud_connection"

    def __init__(self, coordinator: CloudCoordinator, widget_id: str) -> None:
        super().__init__(coordinator, widget_id, "online")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.online
