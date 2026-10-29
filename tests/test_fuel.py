"""Tests for the heat / fuel / storage model."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from custom_components.hargassner_hk.fuel import FuelSettings, FuelTracker

SETTINGS = FuelSettings(
    nominal_power_kw=30.0, calorific_value_kwh_per_kg=3.0, bulk_density_kg_per_srm=200.0, efficiency=0.9
)
T0 = datetime(2026, 10, 1, 12, 0)


def test_constant_output_for_one_hour() -> None:
    tracker = FuelTracker(SETTINGS)
    for minute in range(61):
        tracker.add_sample(50.0, T0 + timedelta(minutes=minute))
    assert tracker.heat_kwh == pytest.approx(15.0)  # 50 % of 30 kW for 1 h
    assert tracker.fuel_kg == pytest.approx(15.0 / (3.0 * 0.9))
    assert tracker.fuel_srm == pytest.approx(tracker.fuel_kg / 200)


def test_gap_is_not_integrated() -> None:
    tracker = FuelTracker(SETTINGS)
    tracker.add_sample(100.0, T0)
    tracker.add_sample(100.0, T0 + timedelta(hours=1))  # connection was lost
    assert tracker.heat_kwh == 0


def test_none_resets_integration() -> None:
    tracker = FuelTracker(SETTINGS)
    tracker.add_sample(100.0, T0)
    tracker.add_sample(None, T0 + timedelta(seconds=10))
    tracker.add_sample(100.0, T0 + timedelta(seconds=20))
    assert tracker.heat_kwh == 0


def test_output_is_clamped() -> None:
    tracker = FuelTracker(SETTINGS)
    tracker.add_sample(250.0, T0)
    tracker.add_sample(-5.0, T0 + timedelta(minutes=1))
    assert tracker.heat_kwh == pytest.approx(30.0 / 2 / 60)


def test_storage_decreases_and_never_negative() -> None:
    tracker = FuelTracker(SETTINGS)
    assert tracker.storage_srm is None
    tracker.set_storage_srm(0.01)  # 2 kg
    for minute in range(61):
        tracker.add_sample(100.0, T0 + timedelta(minutes=minute))
    assert tracker.storage_kg == 0
    tracker.refill_srm(10)
    assert tracker.storage_srm == pytest.approx(10)


def test_average_and_days_remaining() -> None:
    tracker = FuelTracker(SETTINGS, {"daily_kg": {"2026-10-01": 100, "2026-10-02": 50, "2026-10-03": 999}})
    tracker.set_storage_srm(3)  # 600 kg
    today = date(2026, 10, 3)
    assert tracker.average_daily_kg(today) == pytest.approx(75)  # today is not complete
    assert tracker.days_remaining(today) == pytest.approx(8)
    assert tracker.consumption_today_kg(today) == 999


def test_idle_day_counts_in_average() -> None:
    tracker = FuelTracker(SETTINGS, {"daily_kg": {"2026-10-01": 100}})
    tracker.add_sample(0.0, datetime(2026, 10, 2, 8, 0))
    tracker.add_sample(0.0, datetime(2026, 10, 2, 8, 1))
    assert tracker.average_daily_kg(date(2026, 10, 3)) == pytest.approx(50)


def test_history_is_pruned() -> None:
    tracker = FuelTracker(SETTINGS, {"daily_kg": {"2026-01-01": 1}})
    tracker.add_sample(10.0, T0)
    tracker.add_sample(10.0, T0 + timedelta(minutes=1))
    assert "2026-01-01" not in tracker.daily_kg


def test_roundtrip() -> None:
    tracker = FuelTracker(SETTINGS)
    tracker.set_storage_srm(20)
    tracker.add_sample(60.0, T0)
    tracker.add_sample(60.0, T0 + timedelta(minutes=2))
    restored = FuelTracker(SETTINGS, tracker.as_dict())
    assert restored.heat_kwh == pytest.approx(tracker.heat_kwh, abs=1e-3)
    assert restored.storage_kg == pytest.approx(tracker.storage_kg, abs=1e-2)
    assert restored.daily_kg.keys() == tracker.daily_kg.keys()
