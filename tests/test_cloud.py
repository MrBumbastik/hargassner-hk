"""Cloud entities against a mocked API (synthetic widget data, structure as seen on an Eco-HK)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hargassner_hk.const import CONF_DAQ_XML, CONF_INSTALLATION_ID, CONF_USE_CLOUD, DOMAIN

from .conftest import DAQ_XML, FakeBoiler

BASE = "/installations/1/widgets"


def _param(path: str, **kw: Any) -> dict[str, Any]:
    return {"resource": f"{BASE}/{path}", **kw}


WIDGETS: list[dict[str, Any]] = [
    {
        "widget": "HEATER",
        "values": {"name": "Test", "state": "STATE_OFF", "efficiency": 0},
        "parameters": {
            "program": _param(
                "heater/parameters/program",
                value="PROGRAM_AUTOMATIC",
                options=["PROGRAM_OFF", "PROGRAM_BOILER", "PROGRAM_AUTOMATIC", "PROGRAM_STOP_FIRING"],
            )
        },
    },
    {
        "widget": "BUFFER",
        "values": {"state": "STATE_ON", "buffer_charge": 90},
        "parameters": {"name": _param("buffer/default/parameters/name", value="", regex="^.*$")},
        "actions": {"force_charging": {"resource": f"{BASE}/buffer/default/actions/force-charging"}},
    },
    {
        "widget": "HEATING_CIRCUIT_FLOOR",
        "number": 2,
        "values": {"name": "FBH", "state": "STATE_HEATING", "room_temperature_current": None, "pump_active": True},
        "parameters": {
            "mode": _param(
                "heating-circuits/2/parameters/mode",
                value="MODE_AUTOMATIC",
                options=["MODE_OFF", "MODE_AUTOMATIC", "MODE_HEATING", "MODE_REDUCTION"],
            ),
            "room_temperature_heating": _param(
                "heating-circuits/2/parameters/room-temperature-heating", value=21, min=14, max=26, step=0.5, unit="°C"
            ),
            "room_temperature_correction": _param(
                "heating-circuits/2/parameters/room-temperature-correction", value=0, min=-3, max=3, step=0.5, unit="°C"
            ),
            "steepness_floor": _param("heating-circuits/2/parameters/steepness-floor", value=0.8, min=0.2, max=3.5, step=0.05, unit=""),
            "automatic_times_daily": _param("heating-circuits/2/parameters/automatic-times-daily", times=["T00:00PT23H45M"]),
        },
    },
    {
        "widget": "BOILER",
        "number": 1,
        "values": {"name": "", "boiler_temperature_current": 40.7},
        "parameters": {
            "boiler_temperature_target": _param(
                "boilers/1/parameters/temperature-target", value=55, min=10, max=84, step=1, unit="°C"
            )
        },
        "actions": {
            "force_charging": {"resource": f"{BASE}/boilers/1/actions/force-charging"},
            "one_time_circulation": {"resource": f"{BASE}/boilers/1/actions/one-time-circulation"},
        },
    },
]


@pytest.fixture
def cloud_api():
    with (
        patch("custom_components.hargassner_hk.cloud.HargassnerCloud.ensure_token", AsyncMock()),
        patch("custom_components.hargassner_hk.cloud.HargassnerCloud.logout", AsyncMock()),
        patch(
            "custom_components.hargassner_hk.cloud.HargassnerCloud.get_widgets",
            AsyncMock(return_value=(WIDGETS, {"online_state": True})),
        ),
        patch("custom_components.hargassner_hk.cloud.HargassnerCloud.set_value", AsyncMock()) as set_value,
        patch("custom_components.hargassner_hk.cloud.HargassnerCloud.post_action", AsyncMock(), create=True) as post_action,
    ):
        yield set_value, post_action


async def _setup(hass: HomeAssistant, boiler: FakeBoiler) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Eco-HK",
        data={
            CONF_HOST: boiler.host,
            CONF_PORT: boiler.port,
            CONF_DAQ_XML: DAQ_XML,
            CONF_USE_CLOUD: True,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_INSTALLATION_ID: "1",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _cloud_entity(hass: HomeAssistant, entry: MockConfigEntry, domain: str, widget_id: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_cloud_{widget_id}_{key}")
    assert entity_id, (domain, widget_id, key)
    return entity_id


async def test_known_cloud_parameters(hass: HomeAssistant, fake_boiler: FakeBoiler, cloud_api) -> None:
    set_value, _ = cloud_api
    entry = await _setup(hass, fake_boiler)
    registry = er.async_get(hass)

    program = _cloud_entity(hass, entry, "select", "heater", "program")
    assert hass.states.get(program).state == "program_automatic"
    assert hass.states.get(program).name == "Eco-HK Boiler program"

    dhw = _cloud_entity(hass, entry, "number", "boiler_1", "boiler_temperature_target")
    assert float(hass.states.get(dhw).state) == 55
    assert hass.states.get(dhw).attributes["max"] == 84

    for key in ("room_temperature_correction", "steepness_floor"):
        entity_id = _cloud_entity(hass, entry, "number", "heating_circuit_floor_2", key)
        assert not registry.async_get(entity_id).disabled, key

    # Time programs and text parameters are not exposed as numbers
    assert registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_cloud_heating_circuit_floor_2_automatic_times_daily") is None
    assert registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_cloud_buffer_name") is None

    await hass.services.async_call("select", "select_option", {"entity_id": program, "option": "program_stop_firing"}, blocking=True)
    set_value.assert_awaited_with(f"{BASE}/heater/parameters/program", "PROGRAM_STOP_FIRING")
