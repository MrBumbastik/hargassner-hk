"""Eco-HK boiler state codes, checked against the cold start recorded on 31.10.2026."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from custom_components.hargassner_hk.channels import BOILER_STATE_OPTIONS, boiler_state
from custom_components.hargassner_hk.daq import Frame
from custom_components.hargassner_hk.runtime import effective_output, wood_chip_burning


def frame(zk: float, leistung: float = 0, foerder: float = 0, **bits: bool) -> Frame:
    digital = {"z_heiz": False, "feuerung_aktiv_f2": False, **bits}
    return Frame(
        analog={"zk": float(zk), "leistung": float(leistung), "foerder": float(foerder)},
        digital=digital,
        received=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize(
    ("code", "state"),
    [(1, "off"), (3, "ignition_start"), (4, "ignition"), (5, "full_firing"), (6, "ember_preservation"),
     (7, "burnout"), (9, "ash_removal"), (10, "safety_limiter_tripped"), (11, "manual_operation"),
     (12, "log_wood_emergency"), (2, "other"), (8, "other")],
)
def test_wood_chip_state_codes(code: int, state: str) -> None:
    assert boiler_state(code, True) == state
    assert state in BOILER_STATE_OPTIONS


def test_cold_start_sequence() -> None:
    """Rows from the recording: purge, filling the chamber, ignition, full firing."""
    purge = frame(3)
    filling = frame(4, foerder=100, es_run=True)  # display: "Brennk. füllen"
    igniting = frame(4, z_heiz=True)  # display: "Zündung"
    full_firing_before_f2 = frame(5, leistung=100, foerder=84)
    full_firing = frame(5, leistung=85, foerder=100, feuerung_aktiv_f2=True)

    assert not wood_chip_burning(purge)
    assert not wood_chip_burning(filling)  # no fire yet while the chamber is filled
    assert wood_chip_burning(igniting)
    assert wood_chip_burning(full_firing_before_f2)  # F2 follows ~15 s after code 5
    assert wood_chip_burning(full_firing)

    # No heat is counted before full firing: output reads 0 % while filling
    assert effective_output(filling, "leistung", True) == 0
    assert effective_output(full_firing, "leistung", True) == 85


def test_eco_hk_fault_texts() -> None:
    """Wood chip boilers use the service manual list, pellet boilers keep their table."""
    from custom_components.hargassner_hk.channels import error_text

    assert error_text(5, "de", wood_chip=True) == "Überstrom Verbindungsschnecke"
    assert error_text(5, "de", wood_chip=False) == "Aschelade entleeren"
    assert error_text(309, "en", wood_chip=True) == "Aschebox voll!"  # German only
    assert error_text(155, "de", wood_chip=True) == "Keine Verbindung zu HKR 0 - 15"  # range 150-165
    assert error_text(0, "de", wood_chip=True) == "Keine Störung"
    assert error_text(0, "en", wood_chip=True) == "No fault"
    assert error_text(4, "de", wood_chip=True) == "Störung 4"  # not in the manual
    assert error_text(4, "en", wood_chip=True) == "Fault 4"
