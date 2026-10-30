"""Operating hours per component, counted from the live stream.

The boiler only streams one running counter (feed screw, BSZ_ES_PEL). For all
other components the run bits / boiler state are integrated here, frame by frame
(about one per second): the feed screw runs in pulses of a few seconds that a
10 s coordinator interval would miss. Totals are persisted and can be set once
to the boiler's own counters, so they match the display and keep counting.

This module has no Home Assistant dependency.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import Any

from .const import (
    KEY_FEED,
    KEY_FIRING_ACTIVE,
    KEY_IGNITION_HEATER,
    KEY_STATE,
    WOOD_CHIP_FULL_FIRING,
    WOOD_CHIP_MARKERS,
)
from .daq import Frame

# Longer gaps between frames are not counted. Must stay below the telnet reconnect delay
# (RECONNECT_MIN_DELAY = 5 s), so time across a reconnect is never credited.
MAX_GAP = 3.0  # s

# Boiler states (ZK), same codes as channels.BOILER_STATES / BURNING_STATES (kept HA-free here)
_IGNITION = {5}
_FULL_FIRING = {7}
_BURNING = {5, 6, 7}


@dataclass(frozen=True)
class Counter:
    key: str
    requires: str  # channel key that must exist in the template ("a:" analog / "d:" digital)
    active: Callable[[Frame], bool]
    has_boiler_counter: bool = False  # boiler shows a counter the user can align with (set_operating_hours)


def _state_in(states: set[int]) -> Callable[[Frame], bool]:
    def check(frame: Frame) -> bool:
        value = frame.analog.get("zk")
        return isinstance(value, float) and int(value) in states
    return check


def _bit(key: str) -> Callable[[Frame], bool]:
    return lambda frame: bool(frame.digital.get(key))


def _positive(key: str) -> Callable[[Frame], bool]:
    def check(frame: Frame) -> bool:
        value = frame.analog.get(key)
        return isinstance(value, float) and value > 0
    return check


COUNTERS: tuple[Counter, ...] = (
    Counter("burner", "a:zk", _state_in(_BURNING), True),
    Counter("full_firing", "a:zk", _state_in(_FULL_FIRING)),
    Counter("ignition", "a:zk", _state_in(_IGNITION), True),
    Counter("draft_fan", "a:sz", _positive("sz"), True),
    # Feed screw: the boiler streams its own counter (BSZ_ES_PEL), no alignment needed
    Counter("feed_screw", "d:es_run", _bit("es_run")),
    Counter("room_discharge", "d:ra_run", _bit("ra_run"), True),
    Counter("ash_discharge", "d:aa_run", _bit("aa_run")),
    Counter("feed_grate", "d:er_run", _bit("er_run")),
    Counter("ash_grate", "d:ar_run", _bit("ar_run")),
    Counter("cleaning_motor", "d:putzm_run", _bit("putzm_run")),
    Counter("circuit_pump_1", "d:hkp1", _bit("hkp1")),
    Counter("circuit_pump_2", "d:hkp2", _bit("hkp2")),
)


# Wood chip boilers: other state codes, and the ignition heater has its own bit.
PROFILE_WOOD_CHIP = "wood_chip_v1"


_full_firing = _state_in(set(WOOD_CHIP_FULL_FIRING))
_feeding = _positive(KEY_FEED)


def wood_chip_burning(frame: Frame) -> bool:
    """Burner active on a wood chip boiler. Single rule for the entity and the hours.

    Full firing (confirmed code 5), ignition heater, or the boiler's own "firing active"
    bit (F2; set during ignition, full firing and the first part of burn-out). Without
    the F2 channel: actual fuel feed instead. Output % is no indicator: it reads 100 %
    during burn-out (recorded 30.10.).
    """
    if _full_firing(frame) or frame.digital.get(KEY_IGNITION_HEATER):
        return True
    if KEY_FIRING_ACTIVE in frame.digital:
        return bool(frame.digital[KEY_FIRING_ACTIVE])
    return _feeding(frame)


def effective_output(frame: Frame, power_key: str, wood_chip: bool) -> float | None:
    """Output % for the heat/fuel model (the single 'heat output' rule).

    Wood chip boilers report output 100 % during burn-out while no fuel is fed and the
    flue gas is already air. Count output only in full firing or while fuel is fed;
    templates without a feed channel fall back to the firing bit, then to raw output.
    """
    output = frame.analog.get(power_key)
    if not isinstance(output, float):
        return None
    if not wood_chip or _full_firing(frame):
        return output
    if KEY_FEED in frame.analog:
        return output if _feeding(frame) else 0.0
    if KEY_FIRING_ACTIVE in frame.digital:
        return output if frame.digital[KEY_FIRING_ACTIVE] else 0.0
    return output


WOOD_CHIP_COUNTERS: dict[str, Counter] = {
    "burner": Counter("burner", f"a:{KEY_STATE}", wood_chip_burning, True),
    "full_firing": Counter("full_firing", f"a:{KEY_STATE}", _full_firing),
    "ignition": Counter("ignition", f"d:{KEY_IGNITION_HEATER}", _bit(KEY_IGNITION_HEATER), True),
}
# Counted with the pellet table before the wood chip profile existed -> reset once
_WOOD_CHIP_RESET = ("ignition", "full_firing")


def is_wood_chip(digital_keys: set[str]) -> bool:
    return WOOD_CHIP_MARKERS <= digital_keys


def available_counters(analog_keys: set[str], digital_keys: set[str]) -> tuple[Counter, ...]:
    """Counters whose source channel exists in the template (wood chip profile if applicable)."""
    keys = {f"a:{k}" for k in analog_keys} | {f"d:{k}" for k in digital_keys}
    wood_chip = is_wood_chip(digital_keys)
    counters = (WOOD_CHIP_COUNTERS.get(c.key, c) if wood_chip else c for c in COUNTERS)
    return tuple(c for c in counters if c.requires in keys)


class RuntimeTracker:
    """Accumulates running seconds per component."""

    def __init__(
        self,
        counters: tuple[Counter, ...],
        stored: dict[str, Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        profile: str | None = None,
    ) -> None:
        self.counters = counters
        self._clock = clock
        stored = stored or {}
        stored_seconds = stored.get("seconds") or {}
        stored_offsets = stored.get("offsets") or {}
        # seconds: counted since installation (statistics); offsets: boiler counter at that time.
        # Keys of counters missing from the current template are kept, so a template change
        # does not erase their totals.
        self.seconds: dict[str, float] = {k: float(v) for k, v in stored_seconds.items()}
        for c in counters:
            self.seconds.setdefault(c.key, 0.0)
        self.offsets: dict[str, float] = {k: float(v) for k, v in stored_offsets.items()}
        self.profile = profile
        if profile == PROFILE_WOOD_CHIP and stored.get("profile") != PROFILE_WOOD_CHIP:
            for key in _WOOD_CHIP_RESET:  # counted with the wrong (pellet) state codes
                if key in self.seconds:
                    self.seconds[key] = 0.0
                self.offsets.pop(key, None)
        self._last_time: float | None = None
        self._last_active: dict[str, bool] = {}
        self.changed = False

    def add_frame(self, frame: Frame) -> None:
        """Count the interval since the previous frame for components active in it."""
        now = self._clock()
        if self._last_time is not None:
            elapsed = now - self._last_time
            if 0 < elapsed <= MAX_GAP:
                for key, was_active in self._last_active.items():
                    if was_active:
                        self.seconds[key] += elapsed
                        self.changed = True
        self._last_time = now
        self._last_active = {c.key: c.active(frame) for c in self.counters}

    def has_counter(self, key: str) -> bool:
        return any(c.key == key and c.has_boiler_counter for c in self.counters)

    def hours(self, key: str) -> float:
        """Hours counted since installation (monotonic: basis for daily/monthly statistics)."""
        return self.seconds.get(key, 0.0) / 3600.0

    def counter_hours(self, key: str) -> float | None:
        """Boiler counter = start value + counted hours; None until a start value is set."""
        if key not in self.offsets:
            return None
        return (self.offsets[key] + self.seconds.get(key, 0.0)) / 3600.0

    def set_counter(self, key: str, hours: float) -> None:
        """Align with the boiler's counter without touching the counted hours (no statistics jump)."""
        if not self.has_counter(key):
            raise KeyError(key)
        self.offsets[key] = float(hours) * 3600.0 - self.seconds[key]
        self.changed = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "seconds": {k: round(v, 1) for k, v in self.seconds.items()},
            "offsets": {k: round(v, 1) for k, v in self.offsets.items()},
        }
