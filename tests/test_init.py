"""End-to-end tests: config flow and entities against a fake boiler."""
from __future__ import annotations

import asyncio
from datetime import timedelta

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.hargassner_hk.const import CONF_DAQ_XML, CONF_USE_CLOUD, DOMAIN

from .conftest import DAQ_XML, PM_LINE_FAULT, FakeBoiler


async def _setup(hass: HomeAssistant, boiler: FakeBoiler) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Eco-HK",
        unique_id=boiler.host,
        data={CONF_HOST: boiler.host, CONF_PORT: boiler.port, CONF_DAQ_XML: DAQ_XML, CONF_USE_CLOUD: False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, domain: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id, key
    return entity_id


async def test_config_flow_local_only(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Eco-HK", CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: "junk" + DAQ_XML},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "cloud"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_USE_CLOUD: False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DAQ_XML] == DAQ_XML  # junk around the block is stripped
    await hass.async_block_till_done()


async def test_config_flow_template_mismatch(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    fake_boiler.line += " 0000"
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Eco-HK", CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: DAQ_XML},
    )
    assert result["errors"] == {CONF_DAQ_XML: "template_mismatch"}
    assert result["description_placeholders"]["received"] == "16"
    assert result["description_placeholders"]["expected"] == "15"


async def test_config_flow_cannot_connect(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    await fake_boiler.stop()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Eco-HK", CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: DAQ_XML},
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_entities(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    entry = await _setup(hass, fake_boiler)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get(_entity_id(hass, entry, "sensor", "a_tk")).state == "78.2"
    assert hass.states.get(_entity_id(hass, entry, "sensor", "a_tk")).attributes["unit_of_measurement"] == "°C"
    assert hass.states.get(_entity_id(hass, entry, "sensor", "a_trg")).name == "Eco-HK Flue gas temperature"
    assert hass.states.get(_entity_id(hass, entry, "sensor", "a_tvl_1")).name == "Eco-HK Flow temperature circuit 1"
    assert hass.states.get(_entity_id(hass, entry, "sensor", "boiler_state")).state == "full_firing"
    assert hass.states.get(_entity_id(hass, entry, "sensor", "fault_message")).state == "No fault"
    assert hass.states.get(_entity_id(hass, entry, "binary_sensor", "burning")).state == "on"
    assert hass.states.get(_entity_id(hass, entry, "binary_sensor", "fault_active")).state == "off"
    assert hass.states.get(_entity_id(hass, entry, "binary_sensor", "d_hkp1")).state == "on"
    assert hass.states.get(_entity_id(hass, entry, "binary_sensor", "local_connection")).state == "on"

    registry = er.async_get(hass)
    # Motor currents and unknown channels are disabled by default
    assert registry.async_get(_entity_id(hass, entry, "sensor", "a_i_ra")).disabled
    assert registry.async_get(_entity_id(hass, entry, "sensor", "a_xyz_intern")).disabled
    assert registry.async_get(_entity_id(hass, entry, "binary_sensor", "d_raumaustragung")).disabled

    # Fault appears on the next update
    fake_boiler.line = PM_LINE_FAULT
    await asyncio.sleep(0.2)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert hass.states.get(_entity_id(hass, entry, "sensor", "fault_message")).state == "Feed motor blocked"
    assert hass.states.get(_entity_id(hass, entry, "binary_sensor", "fault_active")).state == "on"
    assert hass.states.get(_entity_id(hass, entry, "sensor", "boiler_state")).state == "ember_preservation"

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_storage_services(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    entry = await _setup(hass, fake_boiler)
    storage = _entity_id(hass, entry, "number", "storage_level")
    assert hass.states.get(storage).state == "unknown"

    await hass.services.async_call(
        DOMAIN, "set_storage", {"config_entry_id": entry.entry_id, "amount": 40}, blocking=True
    )
    await hass.services.async_call(
        DOMAIN, "refill", {"config_entry_id": entry.entry_id, "amount": 10}, blocking=True
    )
    await hass.async_block_till_done()
    assert float(hass.states.get(storage).state) == 50
    assert float(hass.states.get(_entity_id(hass, entry, "sensor", "storage_kg")).state) == 50 * 210

    await hass.services.async_call(
        "number", "set_value", {"entity_id": storage, "value": 12.5}, blocking=True
    )
    assert float(hass.states.get(storage).state) == 12.5


async def test_heat_is_integrated(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    entry = await _setup(hass, fake_boiler)
    local = entry.runtime_data.local
    start = local.fuel.heat_kwh
    # Two more coordinator updates 10 s apart at 80 % of 30 kW
    for _ in range(2):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
        await hass.async_block_till_done()
    assert local.fuel.heat_kwh > start
    heat = hass.states.get(_entity_id(hass, entry, "sensor", "heat_energy"))
    assert heat.attributes["device_class"] == "energy"
    assert heat.attributes["state_class"] == "total_increasing"


async def test_setup_retries_without_boiler(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    fake_boiler.line += " 0000"  # wrong template -> no valid frame
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: DAQ_XML, CONF_USE_CLOUD: False},
    )
    entry.add_to_hass(hass)
    import custom_components.hargassner_hk as integration

    integration.FIRST_FRAME_TIMEOUT = 0.5
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    integration.FIRST_FRAME_TIMEOUT = 20.0
