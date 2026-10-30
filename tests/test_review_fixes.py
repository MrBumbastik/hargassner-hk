"""Regression tests for the code review findings of 2026-10-30."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.hargassner_hk.const import (
    CONF_DAQ_XML,
    CONF_INSTALLATION_NAME,
    CONF_USE_CLOUD,
    DOMAIN,
)
from custom_components.hargassner_hk.diagnostics import async_get_config_entry_diagnostics

from .conftest import DAQ_XML, FakeBoiler


def _entry(boiler: FakeBoiler, **extra) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Eco-HK",
        unique_id=boiler.host,
        data={CONF_HOST: boiler.host, CONF_PORT: boiler.port, CONF_DAQ_XML: DAQ_XML, CONF_USE_CLOUD: False, **extra},
    )


async def test_fuel_is_saved_while_burning(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    """Finding 1: a save must be scheduled at most once per minute, not postponed by every tick."""
    entry = _entry(fake_boiler)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    local = entry.runtime_data.local
    with patch.object(local._store, "async_delay_save") as delay_save:
        local._last_save -= 120  # last save two minutes ago
        for _ in range(5):
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
            await hass.async_block_till_done()
    assert delay_save.call_count == 1


async def test_diagnostics_redact_names(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    """Finding 3: the installation name must not appear in diagnostics."""
    entry = _entry(fake_boiler, **{CONF_INSTALLATION_NAME: "Max Mustermann"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert "Mustermann" not in str(diag)


async def test_reconfigure_updates_unique_id(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    """Finding 2: a new host becomes the new unique_id; a host of another entry is refused."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="10.0.0.1",
        data={CONF_HOST: "10.0.0.1", CONF_PORT: fake_boiler.port, CONF_DAQ_XML: DAQ_XML, CONF_USE_CLOUD: False},
    )
    entry.add_to_hass(hass)
    other = MockConfigEntry(domain=DOMAIN, unique_id="10.0.0.99", data={})
    other.add_to_hass(hass)

    with patch("custom_components.hargassner_hk.async_setup_entry", AsyncMock(return_value=True)):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: " 10.0.0.99 ", CONF_PORT: fake_boiler.port, CONF_DAQ_XML: DAQ_XML}
        )
        assert result["reason"] == "already_configured"

        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: " 127.0.0.1\n", CONF_PORT: fake_boiler.port, CONF_DAQ_XML: DAQ_XML}
        )
        assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "127.0.0.1"
    assert entry.data[CONF_HOST] == "127.0.0.1"


async def test_setup_failure_stops_telnet(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    """Finding 4: if setup fails after the stream started, the telnet task must be stopped."""
    entry = _entry(fake_boiler)
    entry.add_to_hass(hass)
    from custom_components.hargassner_hk.telnet import HargassnerTelnet

    real_stop = HargassnerTelnet.stop
    stopped: list[HargassnerTelnet] = []

    async def spy_stop(self: HargassnerTelnet) -> None:
        stopped.append(self)
        await real_stop(self)

    with (
        patch(
            "custom_components.hargassner_hk.coordinator.LocalCoordinator.async_config_entry_first_refresh",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch.object(HargassnerTelnet, "stop", spy_stop),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert stopped and stopped[0]._task is None
