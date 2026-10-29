"""Parser for the Hargassner DAQ template and the local "pm" telnet stream.

The Touch-Tronic controller writes a ``<DAQPRJ>`` XML header at the start of
every ``DAQxxxxx.DAQ`` file on the SD card. It describes the fields of the
``pm`` lines the controller sends on TCP port 23:

    pm <analog 0> <analog 1> ... <analog n-1> <digital word 0> ... <digital word m-1>

Analog values are decimal numbers, digital words are hexadecimal bit fields.
The field layout depends on the firmware, so it is read from the template
instead of being hard-coded.

This module has no Home Assistant dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
import xml.etree.ElementTree as ET

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})
_DAQ_RE = re.compile(r"<DAQPRJ>.*?</DAQPRJ>", re.DOTALL | re.IGNORECASE)


class DaqFormatError(ValueError):
    """The DAQ template could not be parsed."""


def slugify(name: str) -> str:
    """Turn a channel name like 'TA Gem.' or 'Störungs Nr' into 'ta_gem' / 'stoerungs_nr'."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.translate(_UMLAUTS).lower())
    return slug.strip("_") or "channel"


@dataclass(frozen=True)
class AnalogChannel:
    """An analog value in the pm line."""

    index: int
    name: str
    key: str
    unit: str | None


@dataclass(frozen=True)
class DigitalChannel:
    """A single bit of a digital word in the pm line."""

    word: int
    bit: int
    name: str
    key: str


@dataclass(frozen=True)
class DaqFormat:
    """Layout of a pm line."""

    analog: tuple[AnalogChannel, ...]
    digital: tuple[DigitalChannel, ...]
    analog_count: int
    digital_count: int

    @property
    def expected_length(self) -> int:
        """Number of values after the leading 'pm' token."""
        return self.analog_count + self.digital_count

    def analog_by_name(self, name: str) -> AnalogChannel | None:
        """Look up an analog channel by its template name (case-insensitive)."""
        wanted = slugify(name)
        return next((ch for ch in self.analog if ch.key == wanted or slugify(ch.name) == wanted), None)


@dataclass
class Frame:
    """One decoded pm line."""

    analog: dict[str, float | str]
    digital: dict[str, bool]
    received: datetime
    raw: str = field(repr=False, default="")


def extract_daq_xml(text: str) -> str:
    """Cut the <DAQPRJ> block out of a pasted template or a whole DAQ file."""
    match = _DAQ_RE.search(text)
    if not match:
        raise DaqFormatError("No <DAQPRJ>…</DAQPRJ> block found")
    return match.group(0)


def _channels(section: ET.Element | None) -> list[ET.Element]:
    if section is None:
        return []
    # Templates use <CHANNEL>; some tools shorten it to <CH>.
    return [el for el in section if el.tag.upper() in ("CHANNEL", "CH")]


def _unique(key: str, used: set[str], suffix: str) -> str:
    if key in used:
        key = f"{key}_{suffix}"
    used.add(key)
    return key


def parse_daq_xml(text: str) -> DaqFormat:
    """Parse a <DAQPRJ> template into a DaqFormat."""
    xml_text = extract_daq_xml(text)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as err:
        raise DaqFormatError(f"Invalid XML: {err}") from err

    used: set[str] = set()
    analog: list[AnalogChannel] = []
    for el in _channels(root.find("ANALOG")):
        try:
            index = int(el.attrib["id"])
        except (KeyError, ValueError) as err:
            raise DaqFormatError(f"Analog channel without valid id: {el.attrib}") from err
        name = (el.attrib.get("name") or f"Analog {index}").strip()
        unit = (el.attrib.get("unit") or "").strip() or None
        analog.append(AnalogChannel(index, name, _unique(slugify(name), used, str(index)), unit))

    digital: list[DigitalChannel] = []
    for el in _channels(root.find("DIGITAL")):
        try:
            word = int(el.attrib["id"])
            bit = int(el.attrib["bit"])
        except (KeyError, ValueError) as err:
            raise DaqFormatError(f"Digital channel without valid id/bit: {el.attrib}") from err
        if not 0 <= bit < 32:
            raise DaqFormatError(f"Digital bit out of range: {el.attrib}")
        name = (el.attrib.get("name") or f"Digital {word}.{bit}").strip()
        digital.append(DigitalChannel(word, bit, name, _unique(slugify(name), used, f"{word}_{bit}")))

    if not analog:
        raise DaqFormatError("Template contains no analog channels")

    return DaqFormat(
        analog=tuple(analog),
        digital=tuple(digital),
        analog_count=max(ch.index for ch in analog) + 1,
        digital_count=(max(ch.word for ch in digital) + 1) if digital else 0,
    )


def _number(token: str) -> float | str:
    try:
        return float(token)
    except ValueError:
        return token


def split_pm_line(line: str) -> list[str] | None:
    """Return the value tokens of a pm line, or None if it is no pm line.

    Telnet negotiation bytes or a partial previous line can precede 'pm',
    so we look for the token instead of requiring it at position 0.
    """
    pos = line.find("pm ")
    if pos < 0:
        return None
    return line[pos + 3 :].split()


def decode_frame(fmt: DaqFormat, line: str, received: datetime) -> Frame | None:
    """Decode a pm line. Returns None if the line does not match the template."""
    values = split_pm_line(line)
    if values is None or len(values) != fmt.expected_length:
        return None

    analog = {ch.key: _number(values[ch.index]) for ch in fmt.analog}

    words: list[int] = []
    for token in values[fmt.analog_count :]:
        try:
            words.append(int(token, 16))
        except ValueError:
            return None
    digital = {ch.key: bool(words[ch.word] & (1 << ch.bit)) for ch in fmt.digital}

    return Frame(analog=analog, digital=digital, received=received, raw=line.strip())
