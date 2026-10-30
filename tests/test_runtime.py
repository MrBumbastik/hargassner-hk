"""Operating hours: counting per frame, gaps, persistence, boiler counter alignment."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hargassner_hk.const import CONF_DAQ_XML, CONF_STREAM_EXTRAS, CONF_USE_CLOUD, DOMAIN
from custom_components.hargassner_hk.daq import Frame, parse_daq_xml
from custom_components.hargassner_hk.runtime import COUNTERS, RuntimeTracker, available_counters

from .conftest import FakeBoiler

FIXTURES = Path(__file__).parent / "fixtures"
LIVE_LINE = next(l for l in (FIXTURES / "eco_hk_50_live_line.txt").read_text().splitlines() if l.startswith("pm "))
NO_STORAGE = (FIXTURES / "eco_hk_50_v30.0HAR.f_ohne_lager.xml").read_text()
EXTRAS = ["ExtHK_1 Solltmp.", "BoiZustand_1", "BoiZustand_1"]


def frame(zk: float = 1, sz: float = 0, **bits: bool) -> Frame:
    return Frame(analog={"zk": float(zk), "sz": float(sz)}, digital=dict(bits), received=datetime.now(timezone.utc))


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_counts_interval_of_active_component() -> None:
    clock = Clock()
    rt = RuntimeTracker(COUNTERS, clock=clock)
    for i in range(3601):  # one hour of frames, feed screw on, boiler in full firing
        clock.t = float(i)
        rt.add_frame(frame(zk=7, sz=60, es_run=True))
    assert rt.hours("feed_screw") == pytest.approx(1.0)
    assert rt.hours("full_firing") == pytest.approx(1.0)
    assert rt.hours("burner") == pytest.approx(1.0)
    assert rt.hours("draft_fan") == pytest.approx(1.0)
    assert rt.hours("ignition") == 0
    assert rt.hours("room_discharge") == 0


def test_short_pulses_are_counted() -> None:
    """Feed screw pulses of 3 s every 10 s: 30 % of the time (a 10 s poll would see ~0 or ~100 %)."""
    clock = Clock()
    rt = RuntimeTracker(COUNTERS, clock=clock)
    for i in range(1000):
        clock.t = float(i)
        rt.add_frame(frame(es_run=(i % 10) < 3))
    assert rt.seconds["feed_screw"] == pytest.approx(300, abs=3)


def test_gaps_are_not_counted() -> None:
    clock = Clock()
    rt = RuntimeTracker(COUNTERS, clock=clock)
    rt.add_frame(frame(es_run=True))
    clock.t = 600  # connection lost for 10 minutes
    rt.add_frame(frame(es_run=True))
    clock.t = 601
    rt.add_frame(frame(es_run=True))
    assert rt.seconds["feed_screw"] == pytest.approx(1)


def test_counter_alignment_keeps_statistics_monotonic() -> None:
    clock = Clock()
    rt = RuntimeTracker(COUNTERS, clock=clock)
    for i in range(11):
        clock.t = float(i)
        rt.add_frame(frame(es_run=True))
    rt.add_frame(frame(ra_run=True))
    before = rt.hours("room_discharge")
    rt.set_counter("room_discharge", 1878.6)
    assert rt.hours("room_discharge") == before  # statistics source untouched
    assert rt.counter_hours("room_discharge") == pytest.approx(1878.6)
    for i in range(11, 3611):
        clock.t = float(i)
        rt.add_frame(frame(ra_run=True))
    assert rt.counter_hours("room_discharge") == pytest.approx(1879.6, abs=0.001)
    assert rt.counter_hours("ignition") is None  # no start value set
    restored = RuntimeTracker(COUNTERS, rt.as_dict(), clock=clock)
    assert restored.counter_hours("room_discharge") == pytest.approx(1879.6, abs=0.001)
    for bad in ("nonsense", "feed_screw", "circuit_pump_1"):  # no boiler counter to align with
        with pytest.raises(KeyError):
            rt.set_counter(bad, 1)


def test_totals_survive_template_without_the_channel() -> None:
    rt = RuntimeTracker(COUNTERS, {"seconds": {"circuit_pump_2": 7200.0}, "offsets": {"burner": 5.0}})
    reduced = RuntimeTracker(tuple(c for c in COUNTERS if c.key != "circuit_pump_2"), rt.as_dict())
    assert reduced.as_dict()["seconds"]["circuit_pump_2"] == 7200.0
    assert reduced.as_dict()["offsets"]["burner"] == 5.0


def test_available_counters_follow_template() -> None:
    fmt = parse_daq_xml(NO_STORAGE)
    keys = {c.key for c in available_counters({c.key for c in fmt.analog}, {c.key for c in fmt.digital})}
    assert keys == {c.key for c in COUNTERS}  # the Eco-HK template has every source
    assert {c.key for c in available_counters({"zk"}, set())} == {"burner", "full_firing", "ignition"}


async def test_runtime_sensors_and_service(hass: HomeAssistant, fake_boiler: FakeBoiler) -> None:
    fake_boiler.line = LIVE_LINE  # idle boiler, circuit pumps 1+2 running
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: fake_boiler.host, CONF_PORT: fake_boiler.port, CONF_DAQ_XML: NO_STORAGE,
              CONF_STREAM_EXTRAS: EXTRAS, CONF_USE_CLOUD: False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry.runtime_data.local.runtime
    assert runtime.seconds["circuit_pump_1"] > 0  # frames arrive every 50 ms in the fake
    assert runtime.seconds["feed_screw"] == 0

    reg = er.async_get(hass)
    hours = hass.states.get(reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_hours_feed_screw"))
    assert hours.attributes["state_class"] == "total_increasing"
    assert hours.attributes["unit_of_measurement"] == "h"
    assert reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_counter_feed_screw") is None  # boiler streams it
    counter_id = reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_counter_room_discharge")
    assert hass.states.get(counter_id).state == "unavailable"  # until a start value is set
    assert "state_class" not in hass.states.get(counter_id).attributes
    assert reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_counter_ash_grate") is None

    await hass.services.async_call(
        DOMAIN, "set_operating_hours",
        {"config_entry_id": entry.entry_id, "component": "room_discharge", "hours": 1878.6}, blocking=True,
    )
    await hass.async_block_till_done()
    assert float(hass.states.get(counter_id).state) == pytest.approx(1878.6, abs=0.1)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "set_operating_hours",
            {"config_entry_id": entry.entry_id, "component": "nonsense", "hours": 1}, blocking=True,
        )
    # Boiler's own feed screw counter: streamed in minutes, shown in hours, no long-term sum
    feed = hass.states.get(reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_a_bsz_es_pel"))
    assert feed.attributes["unit_of_measurement"] == "h"
    assert float(feed.state) == pytest.approx(240617.2 / 60, abs=0.01)
    assert feed.attributes["state_class"] == "measurement"

    local = entry.runtime_data.local
    assert await hass.config_entries.async_unload(entry.entry_id)  # saves on unload
    stored = await local._runtime_store.async_load()
    assert "room_discharge" in stored["offsets"]



def test_wood_chip_profile() -> None:
    """Eco-HK: full firing = code 5, ignition from the ignition heater bit, burner = either."""
    fmt = parse_daq_xml(NO_STORAGE)
    counters = available_counters({c.key for c in fmt.analog}, {c.key for c in fmt.digital})
    clock = Clock()
    rt = RuntimeTracker(counters, clock=clock)
    for i in range(61):  # 1 min ignition heater, then 1 min full firing (code 5)
        clock.t = float(i)
        rt.add_frame(frame(zk=3, z_heiz=True))
    for i in range(61, 121):
        clock.t = float(i)
        rt.add_frame(frame(zk=5))
    assert rt.seconds["ignition"] == pytest.approx(61)
    assert rt.seconds["full_firing"] == pytest.approx(59)
    assert rt.seconds["burner"] == pytest.approx(120)



def test_wood_chip_burner_rule_and_migration() -> None:
    from custom_components.hargassner_hk.runtime import PROFILE_WOOD_CHIP, wood_chip_burning

    assert wood_chip_burning(frame(zk=5))  # confirmed full firing
    assert wood_chip_burning(frame(zk=4, z_heiz=True))  # ignition heater, unknown code
    fed = Frame(analog={"zk": 6.0, "foerder": 30.0}, digital={}, received=datetime.now(timezone.utc))
    assert wood_chip_burning(fed)  # unconfirmed code, but fuel is fed
    burnout = Frame(analog={"zk": 7.0, "leistung": 100.0, "foerder": 0.0}, digital={}, received=datetime.now(timezone.utc))
    assert not wood_chip_burning(burnout)  # output reads 100 % during burn-out: no indicator
    assert not wood_chip_burning(frame(zk=1))
    # Hours counted with the pellet table before the profile existed are reset once
    old = {"seconds": {"ignition": 1800.0, "full_firing": 5.0, "burner": 3600.0}, "offsets": {"ignition": 9.0}}
    rt = RuntimeTracker(COUNTERS, old, profile=PROFILE_WOOD_CHIP)
    assert rt.seconds["ignition"] == 0 and rt.seconds["full_firing"] == 0 and rt.seconds["burner"] == 3600
    assert "ignition" not in rt.offsets
    again = RuntimeTracker(COUNTERS, {**rt.as_dict(), "seconds": {**rt.as_dict()["seconds"], "ignition": 60.0}},
                           profile=PROFILE_WOOD_CHIP)
    assert again.seconds["ignition"] == 60  # only once


# Real values from the 30.10. recording of an Eco-HK 50 (zk, leistung, foerder, o2, F2 bit)
RECORDED = [
    ("full firing", 5, 79, 68, 8.1, True),
    ("burn-out, still feeding", 7, 83, 68, 8.7, True),
    ("burn-out, no feed, flue gas = air", 7, 100, 0, 20.0, True),
    ("burn-out, firing bit cleared", 7, 100, 0, 20.2, False),
    ("off", 1, 0, 0, 20.2, False),
]


def _recorded(zk, out, feed, o2, f2) -> Frame:
    return Frame(
        analog={"zk": float(zk), "leistung": float(out), "foerder": float(feed), "o2": o2},
        digital={"feuerung_aktiv_f2": f2, "z_heiz": False},
        received=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize(("label", "zk", "out", "feed", "o2", "f2"), RECORDED)
def test_burnout_does_not_count_as_heat(label, zk, out, feed, o2, f2) -> None:
    """The boiler reports output 100 % during burn-out; no fuel is fed, so no heat may be counted."""
    from custom_components.hargassner_hk.runtime import effective_output, wood_chip_burning

    frame = _recorded(zk, out, feed, o2, f2)
    expected = float(out) if (zk == 5 or feed > 0) else 0.0
    assert effective_output(frame, "leistung", wood_chip=True) == expected, label
    assert effective_output(frame, "leistung", wood_chip=False) == float(out), label  # pellet: unchanged
    assert wood_chip_burning(frame) is f2, label  # burner active = boiler's own firing bit


def test_burnout_state_is_named() -> None:
    from custom_components.hargassner_hk.channels import BOILER_STATE_OPTIONS, BOILER_STATES_WOOD_CHIP

    assert BOILER_STATES_WOOD_CHIP[7] == "burnout"
    assert "burnout" in BOILER_STATE_OPTIONS


def test_full_firing_counts_even_without_firing_bit() -> None:
    from custom_components.hargassner_hk.runtime import effective_output, wood_chip_burning

    f = Frame(analog={"zk": 5.0, "leistung": 81.0, "foerder": 68.0},
              digital={"feuerung_aktiv_f2": False}, received=datetime.now(timezone.utc))
    assert wood_chip_burning(f)  # confirmed code 5 wins over a missing/shifted F2 bit
    assert effective_output(f, "leistung", wood_chip=True) == 81.0


def test_template_without_feed_channel_falls_back() -> None:
    from custom_components.hargassner_hk.runtime import effective_output

    now = datetime.now(timezone.utc)
    with_f2 = Frame(analog={"zk": 4.0, "leistung": 60.0}, digital={"feuerung_aktiv_f2": True}, received=now)
    no_f2 = Frame(analog={"zk": 4.0, "leistung": 60.0}, digital={}, received=now)
    burnt_out = Frame(analog={"zk": 7.0, "leistung": 100.0}, digital={"feuerung_aktiv_f2": False}, received=now)
    assert effective_output(with_f2, "leistung", wood_chip=True) == 60.0
    assert effective_output(no_f2, "leistung", wood_chip=True) == 60.0  # old rule, nothing to gate on
    assert effective_output(burnt_out, "leistung", wood_chip=True) == 0.0
