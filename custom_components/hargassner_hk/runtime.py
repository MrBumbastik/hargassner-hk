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


def available_counters(analog_keys: set[str], digital_keys: set[str]) -> tuple[Counter, ...]:
    """Counters whose source channel exists in the template."""
    keys = {f"a:{k}" for k in analog_keys} | {f"d:{k}" for k in digital_keys}
    return tuple(c for c in COUNTERS if c.requires in keys)


class RuntimeTracker:
    """Accumulates running seconds per component."""

    def __init__(
        self,
        counters: tuple[Counter, ...],
        stored: dict[str, Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
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
            "seconds": {k: round(v, 1) for k, v in self.seconds.items()},
            "offsets": {k: round(v, 1) for k, v in self.offsets.items()},
        }
