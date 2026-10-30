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
    values = {"ZK": 7, "TK": 78.5, "TRG": 140, "Leistung": 85, "SZ": 60, "UD": 32, "Förder": 40,
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
    assert state("sensor", "a_wasserdruck").attributes["unit_of_measurement"] == "bar"
    assert state("sensor", "a_lagerstand_hk").attributes["unit_of_measurement"] == "m³"
    assert state("sensor", "a_lagerstand_hk").state == "42.5"
    assert state("binary_sensor", "d_es_run").state == "on"
    assert state("binary_sensor", "d_aa_run").state == "off"
    assert state("binary_sensor", "burning").state == "on"
    assert state("sensor", "fault_message").state == "No fault"
