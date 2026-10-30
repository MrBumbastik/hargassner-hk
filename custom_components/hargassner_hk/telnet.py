"""Persistent connection to the local Touch-Tronic telnet stream.

This module has no Home Assistant dependency.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
import logging

from .const import (
    CONNECT_TIMEOUT,
    READ_TIMEOUT,
    RECONNECT_MAX_DELAY,
    RECONNECT_MIN_DELAY,
)
from .daq import DaqFormat, Frame, decode_frame, split_pm_line

_LOGGER = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _decode(raw: bytes) -> str:
    # Drop telnet IAC sequences and other non-printable bytes.
    return raw.decode("latin-1", errors="ignore").replace("\x00", "")


async def read_pm_line(host: str, port: int, timeout: float = 15.0) -> str:
    """Connect once and return the first pm line. Used by the config flow."""
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), CONNECT_TIMEOUT)
    try:
        async with asyncio.timeout(timeout):
            while True:
                raw = await reader.readline()
                if not raw:
                    raise ConnectionError("Connection closed by boiler")
                line = _decode(raw)
                if split_pm_line(line) is not None:
                    return line.strip()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


class HargassnerTelnet:
    """Keeps a connection to the boiler open and decodes every pm line."""

    def __init__(
        self,
        host: str,
        port: int,
        fmt: DaqFormat,
        on_frame: Callable[[Frame], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.fmt = fmt
        self._on_frame = on_frame
        self._task: asyncio.Task | None = None
        self._first_frame = asyncio.Event()
        self.latest: Frame | None = None
        self.connected = False
        self.frames_received = 0
        self.frames_rejected = 0
        self.last_rejected_length: int | None = None
        self.rejected_streak = 0  # consecutive rejected lines of the same length
        self.last_error: str | None = None

    def start(self) -> None:
        """Start the background reader."""
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"hargassner_hk telnet {self.host}")

    async def stop(self) -> None:
        """Stop the background reader and close the connection."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.connected = False

    async def wait_for_frame(self, timeout: float) -> bool:
        """Wait until the first valid frame arrived."""
        try:
            async with asyncio.timeout(timeout):
                await self._first_frame.wait()
        except TimeoutError:
            return False
        return True

    async def _run(self) -> None:
        delay = RECONNECT_MIN_DELAY
        while True:
            try:
                await self._read_stream()
                delay = RECONNECT_MIN_DELAY
            except asyncio.CancelledError:
                raise
            except (OSError, TimeoutError, ConnectionError, ValueError) as err:
                # ValueError: line longer than the stream reader limit (garbage on the line)
                self.last_error = str(err) or type(err).__name__
                if self.connected:
                    _LOGGER.warning("Lost connection to %s:%s: %s", self.host, self.port, self.last_error)
                else:
                    _LOGGER.debug("Cannot connect to %s:%s: %s", self.host, self.port, self.last_error)
            self.connected = False
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)

    async def _read_stream(self) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT
        )
        try:
            self.connected = True
            self.last_error = None
            _LOGGER.debug("Connected to %s:%s", self.host, self.port)
            while True:
                raw = await asyncio.wait_for(reader.readline(), READ_TIMEOUT)
                if not raw:
                    raise ConnectionError("Connection closed by boiler")
                self._handle_line(_decode(raw))
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    def _handle_line(self, line: str) -> None:
        values = split_pm_line(line)
        if values is None:
            return
        frame = decode_frame(self.fmt, line, _utcnow())
        if frame is None:
            self.frames_rejected += 1
            if self.last_rejected_length != len(values):
                _LOGGER.warning(
                    "pm line has %s values, DAQ template expects %s. "
                    "Was the boiler firmware updated? Re-import the DAQ template",
                    len(values),
                    self.fmt.expected_length,
                )
            self.rejected_streak = self.rejected_streak + 1 if self.last_rejected_length == len(values) else 1
            self.last_rejected_length = len(values)
            return
        self.frames_received += 1
        self.rejected_streak = 0
        self.latest = frame
        self._first_frame.set()
        if self._on_frame is not None:
            self._on_frame(frame)
