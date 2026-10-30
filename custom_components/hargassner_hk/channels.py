"""Metadata for known DAQ channels.

Channels are matched by the slug of their template name (see daq.slugify).
Channels not listed here still become entities: they are named after the
template name and get device class / unit from the template unit. Unknown
channels are disabled by default to keep the
entity list manageable (a template has 100+ analog values and bits).

The names come from the Touch-Tronic DAQ templates (Nano-PK, HV, Eco-HK
share most abbreviations). If your Eco-HK template uses other names for
the same values, add them here.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfMass,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)


@dataclass(frozen=True)
class SensorMeta:
    """How an analog channel is presented."""

    translation_key: str | None = None
    icon: str | None = None
    enabled: bool = True
    placeholders: dict[str, str] | None = None


@dataclass(frozen=True)
class BinaryMeta:
    """How a digital channel is presented."""

    translation_key: str | None = None
    device_class: BinarySensorDeviceClass | None = BinarySensorDeviceClass.RUNNING
    icon: str | None = None
    enabled: bool = True
    placeholders: dict[str, str] | None = None


# --- analog -----------------------------------------------------------------

ANALOG: dict[str, SensorMeta] = {
    # Boiler / combustion
    "tk": SensorMeta("boiler_temperature"),
    "tksoll": SensorMeta("boiler_temperature_target"),
    "trg": SensorMeta("flue_gas_temperature", "mdi:smoke"),
    "o2": SensorMeta("oxygen", "mdi:molecule"),
    "o2soll": SensorMeta("oxygen_target", "mdi:molecule"),
    "leistung": SensorMeta("output", "mdi:fire"),
    "szist": SensorMeta("draft_fan", "mdi:fan"),
    "sz": SensorMeta("draft_fan", "mdi:fan"),  # Eco-HK
    "szsoll": SensorMeta("draft_fan_target", "mdi:fan", enabled=False),
    "essoll": SensorMeta("feed_target", "mdi:screw-machine-flat-top"),
    "foerder": SensorMeta("feed_rate", "mdi:screw-machine-flat-top"),  # Eco-HK
    "foerdermenge_ist": SensorMeta(None, "mdi:screw-machine-flat-top", enabled=False),
    "unterdruck": SensorMeta("negative_pressure", "mdi:gauge-low"),
    "ud": SensorMeta("negative_pressure", "mdi:gauge-low"),  # Eco-HK
    "ud_rel": SensorMeta(None, "mdi:gauge-low", enabled=False),
    "ud_no_filt": SensorMeta(None, "mdi:gauge-low", enabled=False),
    "brt": SensorMeta("combustion_chamber_temperature", "mdi:fire"),
    "gbf": SensorMeta(None, "mdi:fire"),  # ember bed sensor
    "plk": SensorMeta(None, "mdi:valve"),  # air flaps
    "tlk": SensorMeta(None, "mdi:valve"),
    "wasserdruck": SensorMeta("water_pressure", "mdi:gauge"),
    "lagerstand_hk": SensorMeta("storage_level_boiler", "mdi:warehouse"),
    "max_anf_kessel": SensorMeta(None, "mdi:thermometer-chevron-up"),
    "atue": SensorMeta(None, "mdi:thermometer-alert"),  # temperature monitoring discharge
    "etue": SensorMeta(None, "mdi:thermometer-alert"),  # temperature monitoring feed channel
    "effizienz": SensorMeta(None, "mdi:percent"),
    # Bulk counters / internals of the Eco-HK, mostly for diagnostics
    "programm": SensorMeta(None, enabled=False),
    "puffzustand": SensorMeta(None, enabled=False),
    "trl": SensorMeta("return_temperature"),
    "trlsoll": SensorMeta("return_temperature_target", enabled=False),
    # Motor currents: useful to spot a blocked discharge screw early
    "i_es": SensorMeta("current_feed", "mdi:current-dc", enabled=False),
    "i_ra": SensorMeta("current_room_discharge", "mdi:current-dc", enabled=False),
    "i_aa": SensorMeta("current_ash_discharge", "mdi:current-dc", enabled=False),
    "i_sr": SensorMeta("current_sliding_grate", "mdi:current-dc", enabled=False),
    "i_rein": SensorMeta("current_cleaning", "mdi:current-dc", enabled=False),
    # Outdoor
    "taus": SensorMeta("outdoor_temperature"),
    "ta": SensorMeta("outdoor_temperature"),
    "ta_gem": SensorMeta("outdoor_temperature_average"),
    # Buffer
    "tpo": SensorMeta("buffer_top"),
    "tpmo": SensorMeta("buffer_upper_middle"),
    "tpm": SensorMeta("buffer_middle"),
    "tpmu": SensorMeta("buffer_lower_middle"),
    "tpu": SensorMeta("buffer_bottom"),
    "puff_fuellgrad": SensorMeta("buffer_charge", "mdi:water-percent"),
    "pufferfuellgrad": SensorMeta("buffer_charge", "mdi:water-percent"),  # Eco-HK
    "puffer_fuellgrad": SensorMeta("buffer_charge", "mdi:water-percent"),
}

# Numbered channels (circuits, DHW tanks): only the first two are enabled by default.
# The template lists every circuit the controller supports, not only the installed ones.
PRIMARY_NUMBERS = {"1", "2"}

# Numbered channels: heating circuits 1..n, DHW tanks 1..n
ANALOG_PATTERNS: list[tuple[re.Pattern[str], str, str | None]] = [
    (re.compile(r"^tvls_?(\d+|[a-z])$"), "flow_temperature_target", None),
    (re.compile(r"^tvl_?(\d+|[a-z])$"), "flow_temperature", None),
    (re.compile(r"^tb_?(\d+)$"), "dhw_temperature", "mdi:water-boiler"),
    (re.compile(r"^tbs_?(\d+)$"), "dhw_temperature_target", "mdi:water-boiler"),
    (re.compile(r"^tra_?(\d+)$"), "room_temperature", "mdi:home-thermometer"),
    (re.compile(r"^trs_?(\d+)$"), "room_temperature_target", "mdi:home-thermometer"),
]


def analog_meta(key: str, unit: str | None) -> SensorMeta:
    """Return presentation metadata for an analog channel."""
    if key in ANALOG:
        return ANALOG[key]
    for pattern, translation_key, icon in ANALOG_PATTERNS:
        if match := pattern.match(key):
            number = match.group(1).upper()
            return SensorMeta(translation_key, icon, enabled=number in PRIMARY_NUMBERS, placeholders={"number": number})
    return SensorMeta(enabled=False)


# Template unit -> (device class, HA unit, state class)
_UNITS: dict[str, tuple[SensorDeviceClass | None, str, SensorStateClass]] = {
    "°c": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "%": (None, PERCENTAGE, SensorStateClass.MEASUREMENT),
    "ma": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.MILLIAMPERE, SensorStateClass.MEASUREMENT),
    "a": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE, SensorStateClass.MEASUREMENT),
    "v": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, SensorStateClass.MEASUREMENT),
    "pa": (SensorDeviceClass.PRESSURE, UnitOfPressure.PA, SensorStateClass.MEASUREMENT),
    "mbar": (SensorDeviceClass.PRESSURE, UnitOfPressure.MBAR, SensorStateClass.MEASUREMENT),
    "bar": (SensorDeviceClass.PRESSURE, UnitOfPressure.BAR, SensorStateClass.MEASUREMENT),
    "m3": (SensorDeviceClass.VOLUME_STORAGE, UnitOfVolume.CUBIC_METERS, SensorStateClass.MEASUREMENT),
    "w": (SensorDeviceClass.POWER, UnitOfPower.WATT, SensorStateClass.MEASUREMENT),
    "kw": (SensorDeviceClass.POWER, UnitOfPower.KILO_WATT, SensorStateClass.MEASUREMENT),
    "kg": (SensorDeviceClass.WEIGHT, UnitOfMass.KILOGRAMS, SensorStateClass.MEASUREMENT),
    "t": (SensorDeviceClass.WEIGHT, UnitOfMass.KILOGRAMS, SensorStateClass.MEASUREMENT),
    "kwh": (SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, SensorStateClass.TOTAL_INCREASING),
    "mwh": (SensorDeviceClass.ENERGY, UnitOfEnergy.MEGA_WATT_HOUR, SensorStateClass.TOTAL_INCREASING),
    "h": (SensorDeviceClass.DURATION, UnitOfTime.HOURS, SensorStateClass.TOTAL_INCREASING),
    "min": (SensorDeviceClass.DURATION, UnitOfTime.MINUTES, SensorStateClass.MEASUREMENT),
    "s": (SensorDeviceClass.DURATION, UnitOfTime.SECONDS, SensorStateClass.MEASUREMENT),
}


def unit_meta(unit: str | None) -> tuple[SensorDeviceClass | None, str | None, SensorStateClass | None]:
    """Map a template unit to HA device class, unit and state class."""
    if not unit:
        return None, None, SensorStateClass.MEASUREMENT
    if mapped := _UNITS.get(unit.strip().lower()):
        return mapped
    return None, unit, SensorStateClass.MEASUREMENT


def unit_scale(unit: str | None) -> float:
    """Factor to convert a template value to the HA unit (only tonnes -> kg)."""
    return 1000.0 if unit and unit.strip().lower() == "t" else 1.0


# --- digital ----------------------------------------------------------------

DIGITAL: dict[str, BinaryMeta] = {
    "stoerung": BinaryMeta("fault", BinarySensorDeviceClass.PROBLEM),
    "stb": BinaryMeta("safety_limiter", BinarySensorDeviceClass.PROBLEM),
    "tks": BinaryMeta("boiler_contact", BinarySensorDeviceClass.RUNNING, enabled=False),
    "hkpa": BinaryMeta("circuit_pump", placeholders={"number": "A"}, icon="mdi:pump", enabled=False),
    "blp": BinaryMeta("dhw_pump", placeholders={"number": "1"}, icon="mdi:pump"),
    "rlp": BinaryMeta("return_pump", icon="mdi:pump"),
    "rlp_puffp": BinaryMeta("return_pump", icon="mdi:pump"),  # Eco-HK
    "notaus": BinaryMeta("emergency_stop", BinarySensorDeviceClass.PROBLEM),
    # Wood chip drives (Eco-HK)
    "es_run": BinaryMeta("feed_screw", icon="mdi:screw-machine-flat-top"),
    "ra_run": BinaryMeta("room_discharge", icon="mdi:screw-machine-flat-top"),
    "aa_run": BinaryMeta("ash_discharge", icon="mdi:delete-variant"),
    "er_run": BinaryMeta("feed_grate", icon="mdi:grid"),
    "ar_run": BinaryMeta("ash_grate", icon="mdi:grid"),
    "putzm_run": BinaryMeta("cleaning_motor", icon="mdi:broom"),
    "fs_asche": BinaryMeta("ash_level", BinarySensorDeviceClass.PROBLEM),
    "sk_aschebox": BinaryMeta("ash_box_switch", BinarySensorDeviceClass.OPENING, enabled=False),
    "sk_lager": BinaryMeta("storage_switch", BinarySensorDeviceClass.OPENING, enabled=False),
    "deckel": BinaryMeta("lid", BinarySensorDeviceClass.OPENING, enabled=False),
}

DIGITAL_PATTERNS: list[tuple[re.Pattern[str], str, str | None]] = [
    (re.compile(r"^hkp_?(\d+)$"), "circuit_pump", "mdi:pump"),
    (re.compile(r"^blp_?(\d+)$"), "dhw_pump", "mdi:pump"),
    (re.compile(r"^bp_?(\d+)$"), "dhw_pump", "mdi:pump"),  # Eco-HK
    (re.compile(r"^bzp_?(\d+)$"), "circulation_pump", "mdi:pump"),
]


def digital_meta(key: str) -> BinaryMeta:
    """Return presentation metadata for a digital channel."""
    if key in DIGITAL:
        return DIGITAL[key]
    for pattern, translation_key, icon in DIGITAL_PATTERNS:
        if match := pattern.match(key):
            number = match.group(1)
            return BinaryMeta(translation_key, icon=icon, enabled=number in PRIMARY_NUMBERS, placeholders={"number": number})
    return BinaryMeta(device_class=None, enabled=False)


# --- boiler state (ZK) ---------------------------------------------------------

# Codes from the Nano-PK firmware; the Eco-HK uses the same controller family.
# Unknown codes are shown as "other" with the raw code as attribute.
BOILER_STATES: dict[int, str] = {
    1: "off",
    2: "preparing_start",
    3: "boiler_start",
    4: "ignition_monitoring",
    5: "ignition",
    6: "transition_full_firing",
    7: "full_firing",
    8: "ember_preservation",
    9: "waiting_ash_removal",
    10: "ash_removal",
    12: "cleaning",
}
BOILER_STATE_OTHER = "other"
BOILER_STATE_OPTIONS = [*dict.fromkeys(BOILER_STATES.values()), BOILER_STATE_OTHER]
BURNING_STATES = {"ignition", "transition_full_firing", "full_firing"}


# --- error codes (Störungs Nr) -------------------------------------------------

ERRORS_DE: dict[int, str] = {
    0: "Keine Störung",
    5: "Aschelade entleeren",
    6: "Aschelade zu voll",
    29: "Verbrennungsstörung",
    30: "Batterie leer",
    31: "Blockade Einschubmotor",
    32: "Füllzeit überschritten",
    70: "Lagerstand niedrig",
    89: "Schieberost schwergängig",
    93: "Aschelade offen",
    155: "Spülung defekt",
    227: "Lagerraumschalter aus",
    228: "Behälter fast leer",
    229: "Füllstandsmelder kontrollieren",
    371: "Brennraum prüfen",
}
ERRORS_EN: dict[int, str] = {
    0: "No fault",
    5: "Empty ash box",
    6: "Ash box too full",
    29: "Combustion fault",
    30: "Battery empty",
    31: "Feed motor blocked",
    32: "Filling time exceeded",
    70: "Storage level low",
    89: "Sliding grate stiff",
    93: "Ash box open",
    155: "Flushing defective",
    227: "Storage room switch off",
    228: "Hopper almost empty",
    229: "Check level sensor",
    371: "Check combustion chamber",
}


def error_text(code: int, language: str) -> str:
    """Human-readable text for a Störungs Nr."""
    table = ERRORS_DE if language.lower().startswith("de") else ERRORS_EN
    if code in table:
        return table[code]
    return f"Störung {code}" if table is ERRORS_DE else f"Fault {code}"
