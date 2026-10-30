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
