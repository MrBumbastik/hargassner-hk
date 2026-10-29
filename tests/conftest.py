"""Shared fixtures: a synthetic DAQ template and a fake Touch-Tronic telnet server."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]

# Small template in the format of a real DAQ header, with HK-relevant channels.
DAQ_XML = (
    "<DAQPRJ><ANALOG>"
    "<CHANNEL id='0' name='ZK' unit=''/>"
    "<CHANNEL id='1' name='O2' unit='%'/>"
    "<CHANNEL id='2' name='TK' unit='°C'/>"
    "<CHANNEL id='3' name='TKsoll' unit='°C'/>"
    "<CHANNEL id='4' name='TRG' unit='°C'/>"
    "<CHANNEL id='5' name='Leistung' unit='%'/>"
    "<CHANNEL id='6' name='SZist' unit='%'/>"
    "<CHANNEL id='7' name='I Ra' unit='mA'/>"
    "<CHANNEL id='8' name='TA Gem.' unit='°C'/>"
    "<CHANNEL id='9' name='TPo' unit='°C'/>"
    "<CHANNEL id='10' name='TVL_1' unit='°C'/>"
    "<CHANNEL id='11' name='Störungs Nr' unit=''/>"
    "<CHANNEL id='12' name='Xyz Intern' unit=''/>"
    "</ANALOG><DIGITAL>"
    "<CHANNEL id='0' bit='0' name='Störung'/>"
    "<CHANNEL id='0' bit='7' name='HKP1'/>"
    "<CHANNEL id='1' bit='3' name='Raumaustragung'/>"
    "</DIGITAL></DAQPRJ>"
)

# ZK=7 (full firing), output 80 %, no fault; word0: bit7 (HKP1) set; word1: bit3 set
PM_LINE = "pm 7 8.5 78.2 80 160 80 55 1200 4.5 70.1 45.3 0 3 0080 0008"
PM_LINE_FAULT = "pm 8 12.0 60.0 80 120 0 0 0 4.5 70.1 45.3 31 3 0001 0000"


@dataclass
class FakeBoiler:
    """Fake boiler that sends a pm line to every client every 50 ms."""

    host: str = "127.0.0.1"
    port: int = 0
    line: str = PM_LINE
    connections: int = 0
    _server: asyncio.Server | None = field(default=None, repr=False)
    _handlers: set[asyncio.Task] = field(default_factory=set, repr=False)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        task = asyncio.current_task()
        self._handlers.add(task)
        try:
            # Telnet negotiation garbage before the first line, like the real controller
            writer.write(b"\xff\xfb\x01")
            while True:
                writer.write((self.line + "\r\n").encode("latin-1"))
                await writer.drain()
                await asyncio.sleep(0.05)
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()
            self._handlers.discard(task)

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        for task in list(self._handlers):
            task.cancel()
        await asyncio.gather(*self._handlers, return_exceptions=True)
        await self._server.wait_closed()
        self._server = None


@pytest.fixture
async def fake_boiler(socket_enabled: None) -> AsyncIterator[FakeBoiler]:
    boiler = FakeBoiler()
    await boiler.start()
    yield boiler
    await boiler.stop()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
