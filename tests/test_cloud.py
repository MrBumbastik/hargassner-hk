"""Cloud entities against a mocked API (synthetic widget data, structure as seen on an Eco-HK)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
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
        patch("custom_components.hargassner_hk.cloud.HargassnerCloud.post_action", AsyncMock()) as post_action,
    ):
        yield set_value, post_action


async def _setup(hass: HomeAssistant, boiler: FakeBoiler, allow_write: bool | None = True) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Eco-HK",
        # None: option missing entirely, i.e. the default of an existing install
        options={} if allow_write is None else {"allow_cloud_write": allow_write},
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


async def test_circuit_devices_hang_off_the_boiler(
    hass: HomeAssistant, fake_boiler: FakeBoiler, cloud_api, caplog: pytest.LogCaptureFixture
) -> None:
    """Heating circuit / buffer devices point to the boiler by registry id (no deprecated via_device)."""
    entry = await _setup(hass, fake_boiler)
    dev_reg = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    (boiler,) = [d for d in devices if (DOMAIN, entry.entry_id) in d.identifiers]
    children = [d for d in devices if d.id != boiler.id]
    assert children
    assert all(d.via_device_id == boiler.id for d in children)
    assert "via_device" not in caplog.text


async def test_action_buttons(hass: HomeAssistant, fake_boiler: FakeBoiler, cloud_api) -> None:
    _, post_action = cloud_api
    entry = await _setup(hass, fake_boiler)

    buffer = _cloud_entity(hass, entry, "button", "buffer", "action_force_charging")
    circulation = _cloud_entity(hass, entry, "button", "boiler_1", "action_one_time_circulation")
    assert hass.states.get(circulation).name == "Boiler One-time circulation"
    _cloud_entity(hass, entry, "button", "boiler_1", "action_force_charging")

    await hass.services.async_call("button", "press", {"entity_id": buffer}, blocking=True)
    post_action.assert_awaited_with(f"{BASE}/buffer/default/actions/force-charging")


@pytest.mark.parametrize(
    ("devices", "expected"),
    [
        ([{"type": "Eco-HK 50"}], ("Eco-HK 50", 50.0)),
        ([{"type": "Nano.2 12"}], ("Nano.2 12", 12.0)),
        ([{"type": "Magna 200 kW"}], ("Magna 200 kW", 200.0)),
        ([{"type": "Eco-HK"}], ("Eco-HK", None)),
        ([], (None, None)),
    ],
)
def test_model_info(devices: list, expected: tuple) -> None:
    from custom_components.hargassner_hk.config_flow import model_info

    assert model_info({"devices": devices}) == expected


async def test_config_flow_with_cloud_sets_model_and_power(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    from homeassistant import config_entries
    from homeassistant.const import CONF_NAME
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.hargassner_hk.const import CONF_MODEL, CONF_NOMINAL_POWER

    installations = [{"id": 7, "name": "Test", "devices": [{"type": "Eco-HK 50"}]}]
    with patch(
        "custom_components.hargassner_hk.config_flow._cloud_login", AsyncMock(return_value=(installations, None))
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "Eco-HK", CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: DAQ_XML},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "x"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MODEL] == "Eco-HK 50"
    assert result["data"][CONF_INSTALLATION_ID] == "7"
    assert result["result"].options[CONF_NOMINAL_POWER] == 50.0
    await hass.async_block_till_done()


async def test_cloud_write_is_blocked_by_default(hass: HomeAssistant, fake_boiler: FakeBoiler, cloud_api) -> None:
    """Without the option nothing may be sent to the boiler: numbers, selects, climate, buttons."""
    from homeassistant.exceptions import ServiceValidationError

    set_value, post_action = cloud_api
    entry = await _setup(hass, fake_boiler, allow_write=None)
    calls = [
        ("select", "select_option", {"entity_id": _cloud_entity(hass, entry, "select", "heater", "program"), "option": "program_off"}),
        ("number", "set_value", {"entity_id": _cloud_entity(hass, entry, "number", "boiler_1", "boiler_temperature_target"), "value": 60}),
        ("climate", "set_hvac_mode", {"entity_id": _cloud_entity(hass, entry, "climate", "heating_circuit_floor_2", "climate"), "hvac_mode": "off"}),
        ("climate", "set_temperature", {"entity_id": _cloud_entity(hass, entry, "climate", "heating_circuit_floor_2", "climate"), "temperature": 22}),
        ("button", "press", {"entity_id": _cloud_entity(hass, entry, "button", "buffer", "action_force_charging")}),
    ]
    for domain, service, data in calls:
        with pytest.raises(ServiceValidationError) as err:
            await hass.services.async_call(domain, service, data, blocking=True)
        assert err.value.translation_key == "cloud_write_disabled", (domain, service)
    set_value.assert_not_awaited()
    post_action.assert_not_awaited()
    # Values are still readable
    assert hass.states.get(_cloud_entity(hass, entry, "select", "heater", "program")).state == "program_automatic"


async def test_options_flow_offers_write_switch(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_DAQ_XML: DAQ_XML, CONF_USE_CLOUD: True})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    fields = {str(key): key for key in result["data_schema"].schema}
    assert fields["allow_cloud_write"].default() is False
    user_input = {str(k): (k.default() if callable(getattr(k, "default", None)) else None) for k in result["data_schema"].schema}
    user_input["allow_cloud_write"] = True
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input)
    assert entry.options["allow_cloud_write"] is True


async def test_options_flow_hides_write_switch_without_cloud(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_DAQ_XML: DAQ_XML, CONF_USE_CLOUD: False})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "allow_cloud_write" not in {str(key) for key in result["data_schema"].schema}


async def test_toggling_write_switch_does_not_reload(hass: HomeAssistant, fake_boiler: FakeBoiler, cloud_api) -> None:
    """The switch is read live: enabling it allows writes immediately, without dropping the telnet stream."""
    set_value, _ = cloud_api
    entry = await _setup(hass, fake_boiler, allow_write=None)
    client = entry.runtime_data.local.client
    hass.config_entries.async_update_entry(entry, options={**entry.options, "allow_cloud_write": True})
    await hass.async_block_till_done()
    assert entry.runtime_data.local.client is client  # no reload
    program = _cloud_entity(hass, entry, "select", "heater", "program")
    await hass.services.async_call("select", "select_option", {"entity_id": program, "option": "program_off"}, blocking=True)
    set_value.assert_awaited_with(f"{BASE}/heater/parameters/program", "PROGRAM_OFF")


async def test_credentials_without_switch_enable_cloud(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    """Regression: entered credentials were discarded when an 'use cloud' switch stayed off."""
    from homeassistant import config_entries
    from homeassistant.const import CONF_NAME

    installations = [{"id": 7, "name": "Test", "devices": [{"type": "Eco-HK 50"}]}]
    with patch("custom_components.hargassner_hk.config_flow._cloud_login", AsyncMock(return_value=(installations, None))):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "Eco-HK", CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: DAQ_XML},
        )
        assert "use_cloud" not in {str(k) for k in result["data_schema"].schema}
        # only the password: error, nothing silently dropped
        result2 = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "x"})
        assert result2["errors"] == {"base": "credentials_required"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "x"}
        )
    assert result["data"][CONF_USE_CLOUD] is True
    assert result["data"][CONF_EMAIL] == "user@example.com"
    await hass.async_block_till_done()


async def test_add_cloud_after_setup(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    """Reconfigure → cloud: adds the login to an entry set up without cloud, and removes it again."""
    from custom_components.hargassner_hk.const import CONF_NOMINAL_POWER

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=fake_boiler.host,
        data={CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: DAQ_XML, CONF_USE_CLOUD: False},
        options={CONF_NOMINAL_POWER: 30.0},
    )
    entry.add_to_hass(hass)
    installations = [{"id": 7, "name": "Test", "devices": [{"type": "Eco-HK 50"}]}]
    with (
        patch("custom_components.hargassner_hk.config_flow._cloud_login", AsyncMock(return_value=(installations, None))),
        patch("custom_components.hargassner_hk.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] == "menu"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "reconfigure_cloud"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "x"}
        )
        assert result["reason"] == "reconfigure_successful"
        assert entry.data[CONF_USE_CLOUD] is True and entry.data[CONF_INSTALLATION_ID] == "7"
        assert entry.data[CONF_HOST] == fake_boiler.host  # local data kept
        assert entry.options[CONF_NOMINAL_POWER] == 50.0  # default replaced by the model's power

        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "reconfigure_cloud"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_USE_CLOUD] is False
    assert CONF_EMAIL not in entry.data and CONF_PASSWORD not in entry.data


async def test_wrong_password_is_auth_error(hass: HomeAssistant, aioclient_mock) -> None:
    """The Hargassner cloud answers wrong credentials with HTTP 400 invalid_grant (OAuth), not 401."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from custom_components.hargassner_hk.cloud import CloudAuthError, CloudError, HargassnerCloud
    from custom_components.hargassner_hk.const import API_BASE_URL, API_LOGIN

    aioclient_mock.post(
        API_BASE_URL + API_LOGIN, status=400,
        text='{"error":"invalid_grant","error_description":"The user credentials were incorrect."}',
    )
    with pytest.raises(CloudAuthError):
        await HargassnerCloud(async_get_clientsession(hass), "a@b.c", "wrong").login()

    aioclient_mock.clear_requests()
    aioclient_mock.post(API_BASE_URL + API_LOGIN, status=400, text='{"error":"invalid_client"}')  # app secret, not user
    with pytest.raises(CloudError) as err:
        await HargassnerCloud(async_get_clientsession(hass), "a@b.c", "x").login()
    assert not isinstance(err.value, CloudAuthError)



async def test_removing_cloud_deletes_cloud_entities(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=fake_boiler.host,
        data={CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: DAQ_XML, CONF_USE_CLOUD: True,
              CONF_EMAIL: "a@b.c", CONF_PASSWORD: "x", CONF_INSTALLATION_ID: "7"},
    )
    entry.add_to_hass(hass)
    reg = er.async_get(hass)
    cloud = reg.async_get_or_create("number", DOMAIN, f"{entry.entry_id}_cloud_boiler_1_boiler_temperature_target", config_entry=entry)
    local = reg.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_a_tk", config_entry=entry)
    with patch("custom_components.hargassner_hk.async_setup_entry", AsyncMock(return_value=True)):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "reconfigure_cloud"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["reason"] == "reconfigure_successful"
    assert reg.async_get(cloud.entity_id) is None
    assert reg.async_get(local.entity_id) is not None  # local entities keep their history
