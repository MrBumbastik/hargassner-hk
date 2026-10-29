"""Tests for the DAQ template parser and pm line decoder."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from custom_components.hargassner_hk.daq import (
    DaqFormatError,
    decode_frame,
    parse_daq_xml,
    slugify,
)

from .conftest import DAQ_XML, PM_LINE

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_slugify() -> None:
    assert slugify("Störungs Nr") == "stoerungs_nr"
    assert slugify("TA Gem.") == "ta_gem"
    assert slugify("I Ra") == "i_ra"
    assert slugify("  ") == "channel"


def test_parse_template() -> None:
    fmt = parse_daq_xml(DAQ_XML)
    assert fmt.analog_count == 13
    assert fmt.digital_count == 2
    assert fmt.expected_length == 15
    assert fmt.analog_by_name("leistung").index == 5
    assert fmt.analog_by_name("Störungs Nr").key == "stoerungs_nr"
    assert fmt.analog[2].unit == "°C"
    assert fmt.analog[0].unit is None


def test_parse_whole_daq_file_with_surrounding_data() -> None:
    raw = '\x00\x01garbage"' + DAQ_XML + '"\x00binary log data pm 1 2 3'
    assert parse_daq_xml(raw).expected_length == 15


def test_parse_short_tag_name() -> None:
    fmt = parse_daq_xml("<DAQPRJ><ANALOG><CH id='0' name='TK' unit='°C'/></ANALOG></DAQPRJ>")
    assert fmt.expected_length == 1
    assert fmt.digital == ()


def test_duplicate_names_get_unique_keys() -> None:
    fmt = parse_daq_xml(
        "<DAQPRJ><ANALOG><CHANNEL id='0' name='TVL'/><CHANNEL id='1' name='TVL'/></ANALOG></DAQPRJ>"
    )
    assert [ch.key for ch in fmt.analog] == ["tvl", "tvl_1"]


@pytest.mark.parametrize(
    "xml",
    [
        "no xml here",
        "<DAQPRJ><ANALOG><CHANNEL id='x'/></ANALOG></DAQPRJ>",
        "<DAQPRJ><ANALOG></ANALOG></DAQPRJ>",
        "<DAQPRJ><ANALOG><CHANNEL id='0'/></ANALOG><DIGITAL><CHANNEL id='0' bit='40'/></DIGITAL></DAQPRJ>",
        "<DAQPRJ><ANALOG><CHANNEL id='0'></ANALOG></DAQPRJ>",
    ],
)
def test_invalid_templates(xml: str) -> None:
    with pytest.raises(DaqFormatError):
        parse_daq_xml(xml)


def test_decode_frame() -> None:
    fmt = parse_daq_xml(DAQ_XML)
    frame = decode_frame(fmt, PM_LINE, NOW)
    assert frame is not None
    assert frame.analog["zk"] == 7.0
    assert frame.analog["tk"] == 78.2
    assert frame.analog["stoerungs_nr"] == 0.0
    assert frame.digital == {"stoerung": False, "hkp1": True, "raumaustragung": True}


def test_decode_frame_with_telnet_garbage_prefix() -> None:
    fmt = parse_daq_xml(DAQ_XML)
    assert decode_frame(fmt, "\xff\xfb\x01" + PM_LINE, NOW) is not None


def test_decode_rejects_wrong_length_and_bad_hex() -> None:
    fmt = parse_daq_xml(DAQ_XML)
    assert decode_frame(fmt, PM_LINE + " 0000", NOW) is None
    assert decode_frame(fmt, PM_LINE.replace("0080", "zz80"), NOW) is None
    assert decode_frame(fmt, "zk 1 2 3", NOW) is None
