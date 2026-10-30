"""Tests with the real DAQ template of an Eco-HK 50 (firmware V30.0HAR.f). Values are synthetic."""
from __future__ import annotations

from pathlib import Path

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hargassner_hk.channels import analog_meta, digital_meta
from custom_components.hargassner_hk.const import CONF_DAQ_XML, CONF_USE_CLOUD, DOMAIN
from custom_components.hargassner_hk.daq import parse_daq_xml

from .conftest import FakeBoiler

TEMPLATE = (Path(__file__).parent / "fixtures" / "eco_hk_50_v30.0HAR.f.xml").read_text(encoding="utf-8")


def _line() -> str:
    fmt = parse_daq_xml(TEMPLATE)
    analog = ["0"] * fmt.analog_count
    values = {"ZK": 5, "TK": 78.5, "TRG": 140, "Leistung": 85, "SZ": 60, "UD": 32, "Förder": 40,
              "BRT": 820, "Wasserdruck": 1.8, "Pufferfüllgrad": 64, "TRA_1": 20.5, "Lagerstand HK": 42.5,
              "Störungs Nr": 0}
    for name, value in values.items():
        analog[fmt.analog_by_name(name).index] = str(value)
    words = [0] * fmt.digital_count
    for ch in fmt.digital:
        if ch.name in ("ES Run", "RA Run", "HKP1"):
            words[ch.word] |= 1 << ch.bit
    return "pm " + " ".join(analog + [f"{w:08X}" for w in words])


def test_template_layout() -> None:
    fmt = parse_daq_xml(TEMPLATE)
    assert fmt.analog_count == 133
    assert fmt.digital_count == 8
    assert fmt.expected_length == 141
    for name in ("ZK", "Leistung", "Störungs Nr"):
        assert fmt.analog_by_name(name) is not None, name


def test_wood_chip_channels_are_mapped() -> None:
    fmt = parse_daq_xml(TEMPLATE)
    by_name = {ch.name: ch for ch in fmt.analog}
    expected = {
        "SZ": "draft_fan", "UD": "negative_pressure", "Förder": "feed_rate", "BRT": "combustion_chamber_temperature",
        "Pufferfüllgrad": "buffer_charge", "Wasserdruck": "water_pressure", "Lagerstand HK": "storage_level_boiler",
        "TVL_1": "flow_temperature", "TRA_1": "room_temperature", "TB1": "dhw_temperature",
    }
    for name, key in expected.items():
        ch = by_name[name]
        assert analog_meta(ch.key, ch.unit).translation_key == key, name
    digital = {ch.name: ch for ch in fmt.digital}
    for name, key in {"ES Run": "feed_screw", "RA Run": "room_discharge", "AA Run": "ash_discharge",
                      "Störung": "fault", "HKP1": "circuit_pump", "BP1": "dhw_pump", "BZP1": "circulation_pump"}.items():
        assert digital_meta(digital[name].key).translation_key == key, name


async def test_setup_with_real_template(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    fake_boiler.line = _line()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Eco-HK",
        data={CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: TEMPLATE, CONF_USE_CLOUD: False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)

    def state(domain: str, key: str):
        entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
        assert entity_id, key
        return hass.states.get(entity_id)

    assert state("sensor", "boiler_state").state == "full_firing"
    assert state("sensor", "a_sz").state == "60"
    assert state("sensor", "a_ud").attributes["unit_of_measurement"] == "Pa"
    # Not fitted on the Eco-HK 50 (reads 0.00 / 1000 °C): created, but disabled by default
    for key in ("a_wasserdruck", "a_brt"):
        assert registry.async_get(registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")).disabled, key
    assert state("sensor", "a_lagerstand_hk").attributes["unit_of_measurement"] == "m³"
    assert state("sensor", "a_lagerstand_hk").state == "42.5"
    assert state("binary_sensor", "d_es_run").state == "on"
    assert state("binary_sensor", "d_aa_run").state == "off"
    assert state("binary_sensor", "burning").state == "on"
    assert state("sensor", "fault_message").state == "No fault"


def test_template_without_storage_calculation() -> None:
    """With the boiler's own storage calculation switched off, 'Lagerstand HK' is missing (140 values)."""
    other = (Path(__file__).parent / "fixtures" / "eco_hk_50_v30.0HAR.f_ohne_lager.xml").read_text(encoding="utf-8")
    fmt = parse_daq_xml(other)
    assert fmt.expected_length == 140
    assert fmt.analog_by_name("Lagerstand HK") is None
    # A line from one variant must be rejected by the other
    from datetime import datetime, timezone

    from custom_components.hargassner_hk.daq import decode_frame

    assert decode_frame(fmt, _line(), datetime.now(timezone.utc)) is None


NO_STORAGE = (Path(__file__).parent / "fixtures" / "eco_hk_50_v30.0HAR.f_ohne_lager.xml").read_text(encoding="utf-8")


def _live_like_line() -> str:
    """Synthetic line laid out like the real Eco-HK 50 stream: template + 3 unlisted values."""
    from custom_components.hargassner_hk.daq import STREAM_QUIRKS, with_stream_extras

    fmt = with_stream_extras(parse_daq_xml(NO_STORAGE), STREAM_QUIRKS[0].after)
    analog = ["7"] * fmt.analog_count  # unlisted positions stay "7"
    for name, value in {"ZK": 1, "TK": 43.5, "Taus": 5.3, "TVL_1": 45.9, "TVLs_1": 45.5,
                        "TVL_2": 32.4, "TB1": 45.9, "BoiZustand_1": 0, "TBB": -20.0, "Anf. HKR15": 0}.items():
        analog[fmt.analog_by_name(name).index] = str(value)
    return "pm " + " ".join(analog + ["206", "0", "48", "0", "3000201F", "FC0E0000", "0", "100000"])


def test_stream_quirk_eco_hk() -> None:
    from datetime import datetime, timezone

    from custom_components.hargassner_hk.daq import decode_frame, fit_to_stream, with_stream_extras

    fmt = parse_daq_xml(NO_STORAGE)
    line = _live_like_line()
    assert len(line.split()) - 1 == 143
    assert decode_frame(fmt, line, datetime.now(timezone.utc)) is None  # template alone does not fit
    extras = fit_to_stream(fmt, 143)
    assert extras == ("ExtHK_1 Solltmp.", "BoiZustand_1", "BoiZustand_1")
    frame = decode_frame(with_stream_extras(fmt, extras), line, datetime.now(timezone.utc))
    assert frame.analog["tk"] == 43.5 and frame.analog["taus"] == 5.3
    assert frame.analog["tvl_1"] == 45.9 and frame.analog["tvl_2"] == 32.4
    assert frame.analog["tb1"] == 45.9 and frame.analog["tbb"] == -20.0
    assert frame.digital["hkp1"] and frame.digital["hkp2"]  # word 2 = 0x48
    assert fit_to_stream(fmt, 142) is None


async def test_config_flow_applies_stream_quirk(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    from homeassistant import config_entries
    from homeassistant.const import CONF_NAME
    from homeassistant.data_entry_flow import FlowResultType

    fake_boiler.line = _live_like_line()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Eco-HK", CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: NO_STORAGE},
    )
    assert result["step_id"] == "cloud"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["stream_extras"] == ["ExtHK_1 Solltmp.", "BoiZustand_1", "BoiZustand_1"]
    await hass.async_block_till_done()
    entry = result["result"]
    registry = er.async_get(hass)
    tb1 = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_a_tb1")
    assert hass.states.get(tb1).state == "45.9"
    # Normally closed contacts: bits set (word 0 = 0x206) while the boiler is fine -> no problem
    for key in ("d_stb", "d_notaus"):
        entity_id = registry.async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}_{key}")
        assert hass.states.get(entity_id).state == "off", key


def test_safety_contacts_are_inverted() -> None:
    """Live Eco-HK 50: Stb/NotAus bits are set while everything is fine (normally closed)."""
    for key in ("stb", "notaus", "sk_aschebox", "sk_lager", "sk_radeckel"):
        assert digital_meta(key, wood_chip=True).inverted, key
    assert not digital_meta("stoerung", wood_chip=True).inverted
    # Pellet templates keep the raw bit (not verified there)
    assert not digital_meta("stb").inverted and not digital_meta("notaus").inverted
    assert analog_meta("brt", "°C").enabled and not analog_meta("brt", "°C", wood_chip=True).enabled


LIVE_LINE = next(
    line for line in (Path(__file__).parent / "fixtures" / "eco_hk_50_live_line.txt").read_text().splitlines()
    if line.startswith("pm ")
)


def test_real_captured_line_fixed_positions() -> None:
    """Pins the layout with a real capture (not generated by the code under test)."""
    from datetime import datetime, timezone

    from custom_components.hargassner_hk.daq import decode_frame, fit_to_stream, with_stream_extras

    fmt = parse_daq_xml(NO_STORAGE)
    extras = fit_to_stream(fmt, 143)
    frame = decode_frame(with_stream_extras(fmt, extras), LIVE_LINE, datetime.now(timezone.utc))
    a = frame.analog
    # Values cross-checked against the Hargassner cloud at capture time
    assert (a["tk"], a["tpo"], a["tpm"], a["tpu"], a["taus"]) == (43.5, 72.1, 50.0, 30.3, 5.3)
    assert (a["tvl_1"], a["tvls_1"], a["tra_1"], a["trs_1"]) == (46.4, 45.9, 20.0, 21.0)
    assert (a["tvl_2"], a["tvls_2"]) == (29.8, 33.5)
    assert (a["tb1"], a["tbs_1"], a["boizustand_1"], a["tbb"]) == (45.9, 0.0, 0.0, -20.0)
    assert a["anf_hkr15"] == 0.0
    d = frame.digital
    assert d["stb"] and d["notaus"] and d["hkp1"] and d["hkp2"]  # raw bits; stb/notaus are normally closed


def test_quirk_needs_matching_structure() -> None:
    from custom_components.hargassner_hk.daq import fit_to_stream

    # Same names, but a template of another size must not get the Eco-HK offsets
    small = parse_daq_xml(
        "<DAQPRJ><ANALOG><CHANNEL id='0' name='ExtHK_1 Solltmp.'/><CHANNEL id='1' name='BoiZustand_1'/></ANALOG></DAQPRJ>"
    )
    assert fit_to_stream(small, small.expected_length + 3) is None


async def test_setup_adopts_stream_correction(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    """An entry without correction (older setup) heals itself when the stream needs one."""
    import custom_components.hargassner_hk as integration
    from homeassistant.config_entries import ConfigEntryState

    fake_boiler.line = LIVE_LINE
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: NO_STORAGE, CONF_USE_CLOUD: False},
    )
    entry.add_to_hass(hass)
    integration.FIRST_FRAME_TIMEOUT = 0.5
    try:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert entry.data["stream_extras"] == ["ExtHK_1 Solltmp.", "BoiZustand_1", "BoiZustand_1"]
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
    finally:
        integration.FIRST_FRAME_TIMEOUT = 20.0



def test_wood_chip_state_table() -> None:
    """Eco-HK codes differ from the pellet table: only confirmed codes get a name."""
    from custom_components.hargassner_hk.channels import boiler_state

    assert boiler_state(5, wood_chip=True) == "full_firing"  # display: Leistungsbrand
    assert boiler_state(1, wood_chip=True) == "off"
    assert boiler_state(7, wood_chip=True) == "other"  # unconfirmed on the Eco-HK
    assert boiler_state(5, wood_chip=False) == "ignition"  # pellet table unchanged



async def test_wood_chip_state_entities(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    """Unconfirmed code -> 'other' with raw code; burner active via the ignition heater bit."""
    fmt = parse_daq_xml(TEMPLATE)
    analog = ["0"] * fmt.analog_count
    analog[fmt.analog_by_name("ZK").index] = "3"
    words = [0] * fmt.digital_count
    zh = next(ch for ch in fmt.digital if ch.name == "Z Heiz.")
    words[zh.word] |= 1 << zh.bit
    fake_boiler.line = "pm " + " ".join(analog + [f"{w:08X}" for w in words])
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: TEMPLATE, CONF_USE_CLOUD: False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    reg = er.async_get(hass)
    state = hass.states.get(reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_boiler_state"))
    assert state.state == "other" and state.attributes["code"] == 3
    burning = hass.states.get(reg.async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}_burning"))
    assert burning.state == "on"
