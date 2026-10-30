"""DAQ templates shipped with the integration, so most users need not export one.

Each template was checked against the live stream of a real boiler, together
with its stream correction (see daq.STREAM_QUIRKS). Detection only accepts that
verified combination, never a bare length match, and the config flow
additionally checks the decoded values for plausibility.

This module has no Home Assistant dependency; load_builtin_templates() does
blocking file IO on the first call and must run in an executor.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cache
import logging
from pathlib import Path
from typing import Any

from .daq import DaqFormat, DaqFormatError, Frame, fit_to_stream, parse_daq_xml

_LOGGER = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_BUILTIN = "builtin:"
TEMPLATE_USER = "user"


@dataclass(frozen=True)
class BuiltinTemplate:
    name: str
    xml: str
    fmt: DaqFormat


@dataclass(frozen=True)
class Detection:
    name: str
    xml: str
    fmt: DaqFormat
    extras: tuple[str, ...]

    @property
    def source(self) -> str:
        return f"{TEMPLATE_BUILTIN}{self.name}"


def is_builtin(data: dict[str, Any]) -> bool:
    """Was the entry's template chosen automatically from the shipped ones?"""
    return str(data.get("template_source", "")).startswith(TEMPLATE_BUILTIN)


@cache
def load_builtin_templates() -> tuple[BuiltinTemplate, ...]:
    """Read all shipped templates once (blocking on first call)."""
    result = []
    for path in sorted(TEMPLATE_DIR.glob("*.xml")):
        try:
            xml = path.read_text(encoding="utf-8").strip()
            result.append(BuiltinTemplate(path.stem, xml, parse_daq_xml(xml)))
        except (OSError, UnicodeDecodeError, DaqFormatError) as err:
            _LOGGER.warning("Skipping shipped DAQ template %s: %s", path.name, err)
    return tuple(result)


def detect_template(templates: tuple[BuiltinTemplate, ...] | list[BuiltinTemplate], length: int) -> Detection | None:
    """The shipped template whose verified layout fits a pm line with `length` values."""
    matches = []
    for template in templates:
        extras = fit_to_stream(template.fmt, length)
        # Shipped templates are verified together with their stream correction only;
        # a bare length match (no correction) could be any other boiler.
        if extras:
            matches.append(Detection(template.name, template.xml, template.fmt, extras))
    if len(matches) > 1:
        _LOGGER.warning("Several shipped templates fit %s values: %s", length, [m.name for m in matches])
    return matches[0] if len(matches) == 1 else None


def plausible(frame: Frame) -> bool:
    """Sanity check that an automatically chosen template maps the values sensibly."""
    state, boiler = frame.analog.get("zk"), frame.analog.get("tk")
    return (
        isinstance(state, float) and state.is_integer() and 0 <= state <= 30
        and isinstance(boiler, float) and -30 <= boiler <= 130
    )
