"""Setup without pasting a DAQ template: detection from the shipped templates."""
from __future__ import annotations

from pathlib import Path

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hargassner_hk.const import CONF_DAQ_XML, CONF_USE_CLOUD, DOMAIN
from custom_components.hargassner_hk.daq import STREAM_QUIRKS, parse_daq_xml, with_stream_extras
from custom_components.hargassner_hk.templates import detect_template, load_builtin_templates

from .conftest import PM_LINE, FakeBoiler

FIXTURES = Path(__file__).parent / "fixtures"
LIVE_LINE = next(l for l in (FIXTURES / "eco_hk_50_live_line.txt").read_text().splitlines() if l.startswith("pm "))
EXTRAS = ["ExtHK_1 Solltmp.", "BoiZustand_1", "BoiZustand_1"]


def _line_with_storage() -> str:
    """Stream after enabling the boiler's storage calculation: 141 template values + 3 unlisted."""
    fmt = with_stream_extras(parse_daq_xml((FIXTURES / "eco_hk_50_v30.0HAR.f.xml").read_text()), STREAM_QUIRKS[0].after)
    return "pm " + " ".join(["0"] * fmt.analog_count + ["206", "0", "48", "0", "0", "0", "0", "0"])


def test_shipped_templates_match_fixtures() -> None:
    templates = {t.name: t for t in load_builtin_templates()}
    assert set(templates) == {"Eco-HK V30.0HAR.f", "Eco-HK V30.0HAR.f (Lagerbestand)"}
    assert detect_template(list(templates.values()), 143).name == "Eco-HK V30.0HAR.f"
    assert detect_template(list(templates.values()), 144).name == "Eco-HK V30.0HAR.f (Lagerbestand)"
    assert detect_template(list(templates.values()), 99) is None


async def _start_flow(hass: HomeAssistant, boiler: FakeBoiler, template: str = ""):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Eco-HK", CONF_HOST: boiler.host, CONF_PORT: boiler.port, CONF_DAQ_XML: template},
    )


async def test_setup_without_template(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    fake_boiler.line = LIVE_LINE
    result = await _start_flow(hass, fake_boiler)
    assert result["step_id"] == "cloud"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_USE_CLOUD: False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["template_source"] == "builtin:Eco-HK V30.0HAR.f"
    assert data["stream_extras"] == EXTRAS
    assert "<DAQPRJ>" in data[CONF_DAQ_XML]
    await hass.async_block_till_done()
    assert result["result"].state is ConfigEntryState.LOADED


async def test_unknown_boiler_asks_for_template(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    fake_boiler.line = PM_LINE  # 15 values: no shipped template fits
    result = await _start_flow(hass, fake_boiler)
    assert result["errors"] == {CONF_DAQ_XML: "template_required"}
    assert result["description_placeholders"]["received"] == "15"


async def test_switches_shipped_variant_when_stream_changes(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    """User enables the boiler's storage calculation: +1 channel. The entry follows on its own."""
    import custom_components.hargassner_hk as integration

    templates = {t.name: t for t in await hass.async_add_executor_job(load_builtin_templates)}
    fake_boiler.line = _line_with_storage()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_USE_CLOUD: False,
            CONF_DAQ_XML: templates["Eco-HK V30.0HAR.f"].xml, "stream_extras": EXTRAS,
            "template_source": "builtin:Eco-HK V30.0HAR.f",
        },
    )
    entry.add_to_hass(hass)
    integration.FIRST_FRAME_TIMEOUT = 0.5
    try:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert entry.data["template_source"] == "builtin:Eco-HK V30.0HAR.f (Lagerbestand)"
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
    finally:
        integration.FIRST_FRAME_TIMEOUT = 20.0


async def test_user_template_is_not_switched(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    """A pasted template is the user's choice: never replaced by a shipped one."""
    import custom_components.hargassner_hk as integration

    fake_boiler.line = _line_with_storage()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_USE_CLOUD: False,
            CONF_DAQ_XML: (FIXTURES / "eco_hk_50_v30.0HAR.f_ohne_lager.xml").read_text(), "stream_extras": EXTRAS,
            "template_source": "user",
        },
    )
    entry.add_to_hass(hass)
    integration.FIRST_FRAME_TIMEOUT = 0.5
    try:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert entry.data["template_source"] == "user"
    finally:
        integration.FIRST_FRAME_TIMEOUT = 20.0


async def test_implausible_values_are_not_accepted(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    """Right length for a shipped template, but nonsense values: ask for the real template."""
    tokens = LIVE_LINE.split()
    tokens[1] = "999"  # ZK (boiler state) far out of range
    fake_boiler.line = " ".join(tokens)
    result = await _start_flow(hass, fake_boiler)
    assert result["errors"] == {CONF_DAQ_XML: "template_required"}


async def test_reconfigure_cleared_field_switches_to_detection(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    """A user template can be replaced by auto-detection by clearing the field."""
    from unittest.mock import AsyncMock, patch

    fake_boiler.line = LIVE_LINE
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=fake_boiler.host,
        data={
            CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_USE_CLOUD: False,
            CONF_DAQ_XML: (FIXTURES / "eco_hk_50_v30.0HAR.f_ohne_lager.xml").read_text(), "stream_extras": EXTRAS,
            "template_source": "user",
        },
    )
    entry.add_to_hass(hass)
    with patch("custom_components.hargassner_hk.async_setup_entry", AsyncMock(return_value=True)):
        result = await entry.start_reconfigure_flow(hass)
        # Frontend omits an emptied optional field
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port}
        )
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["template_source"] == "builtin:Eco-HK V30.0HAR.f"
