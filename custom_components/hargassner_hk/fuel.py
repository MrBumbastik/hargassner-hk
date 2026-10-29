"""Heat, fuel consumption and storage model for wood chips.

The Eco-HK does not report how much fuel it burns, so the integration
estimates it from the burner output:

    heat [kWh] = ∫ output [%] / 100 × nominal power [kW] dt
    fuel [kg]  = heat / (calorific value [kWh/kg] × efficiency)
    fuel [SRM] = fuel [kg] / bulk density [kg/SRM]

The storage level (SRM) is set by the user after each delivery and is reduced
by the estimated consumption. Calibrate the calorific value with real
deliveries: if the store empties earlier than predicted, lower it.

This module has no Home Assistant dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

MAX_SAMPLE_GAP = timedelta(minutes=5)  # longer gaps (connection lost) are not integrated
HISTORY_DAYS = 30
AVERAGE_DAYS = 7


@dataclass(frozen=True)
class FuelSettings:
    """User-configurable fuel parameters."""

    nominal_power_kw: float
    calorific_value_kwh_per_kg: float
    bulk_density_kg_per_srm: float
    efficiency: float  # 0..1

    @property
    def kg_per_kwh(self) -> float:
        return 1.0 / (self.calorific_value_kwh_per_kg * self.efficiency)


class FuelTracker:
    """Integrates burner output into heat and fuel figures."""

    def __init__(self, settings: FuelSettings, stored: dict[str, Any] | None = None) -> None:
        self.settings = settings
        stored = stored or {}
        self.heat_kwh: float = float(stored.get("heat_kwh", 0.0))
        self.fuel_kg: float = float(stored.get("fuel_kg", 0.0))
        storage = stored.get("storage_kg")
        self.storage_kg: float | None = None if storage is None else float(storage)
        self.daily_kg: dict[str, float] = {
            str(k): float(v) for k, v in (stored.get("daily_kg") or {}).items()
        }
        self._last_time: datetime | None = None
        self._last_power: float | None = None

    # -- persistence -------------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        return {
            "heat_kwh": round(self.heat_kwh, 4),
            "fuel_kg": round(self.fuel_kg, 4),
            "storage_kg": None if self.storage_kg is None else round(self.storage_kg, 3),
            "daily_kg": {k: round(v, 3) for k, v in self.daily_kg.items()},
        }

    # -- integration -------------------------------------------------------

    def add_sample(self, output_percent: float | None, now: datetime) -> bool:
        """Add a burner output sample. Returns True if the totals changed."""
        if output_percent is None:
            self._last_time = None
            self._last_power = None
            return False

        power_kw = max(0.0, min(float(output_percent), 100.0)) / 100.0 * self.settings.nominal_power_kw
        last_time, last_power = self._last_time, self._last_power
        self._last_time, self._last_power = now, power_kw
        if last_time is None or last_power is None:
            return False

        elapsed = now - last_time
        if elapsed <= timedelta(0) or elapsed > MAX_SAMPLE_GAP:
            return False

        # Record the day even when the boiler is idle, so idle days count in the average.
        day = now.date().isoformat()
        if day not in self.daily_kg:
            self.daily_kg[day] = 0.0
            self._prune(now.date())

        heat = (last_power + power_kw) / 2.0 * elapsed.total_seconds() / 3600.0
        if heat <= 0:
            return False

        fuel = heat * self.settings.kg_per_kwh
        self.heat_kwh += heat
        self.fuel_kg += fuel
        if self.storage_kg is not None:
            self.storage_kg = max(0.0, self.storage_kg - fuel)
        self.daily_kg[day] += fuel
        return True

    def _prune(self, today: date) -> None:
        cutoff = (today - timedelta(days=HISTORY_DAYS)).isoformat()
        for day in [d for d in self.daily_kg if d < cutoff]:
            del self.daily_kg[day]

    # -- storage -----------------------------------------------------------

    @property
    def storage_srm(self) -> float | None:
        if self.storage_kg is None:
            return None
        return self.storage_kg / self.settings.bulk_density_kg_per_srm

    def set_storage_srm(self, srm: float) -> None:
        self.storage_kg = max(0.0, srm) * self.settings.bulk_density_kg_per_srm

    def refill_srm(self, srm: float) -> None:
        self.storage_kg = (self.storage_kg or 0.0) + max(0.0, srm) * self.settings.bulk_density_kg_per_srm

    # -- statistics --------------------------------------------------------

    @property
    def fuel_srm(self) -> float:
        return self.fuel_kg / self.settings.bulk_density_kg_per_srm

    def consumption_today_kg(self, today: date) -> float:
        return self.daily_kg.get(today.isoformat(), 0.0)

    def average_daily_kg(self, today: date, days: int = AVERAGE_DAYS) -> float | None:
        """Average consumption over the last completed days that have data."""
        window = [(today - timedelta(days=i)).isoformat() for i in range(1, days + 1)]
        values = [self.daily_kg[d] for d in window if d in self.daily_kg]
        if not values:
            return None
        return sum(values) / len(values)

    def days_remaining(self, today: date) -> float | None:
        avg = self.average_daily_kg(today)
        if self.storage_kg is None or not avg:
            return None
        return self.storage_kg / avg
