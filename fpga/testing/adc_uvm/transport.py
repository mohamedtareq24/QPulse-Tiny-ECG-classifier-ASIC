"""
Serial transport for UART communication in HIL mode.
Modeled on testing/ecg_hil_uvm/transport.py.
"""

import asyncio
import serial_asyncio


class SerialTransport:
    """Async serial transport wrapper for UART communication."""

    def __init__(self):
        self.reader = None
        self.writer = None
        self._open_event = asyncio.Event()

    async def open(self, port: str, baud_rate: int) -> None:
        """Open serial port connection."""
        if self.writer is not None:
            return
        self.reader, self.writer = await serial_asyncio.open_serial_connection(
            url=port,
            baudrate=baud_rate,
            rtscts=False,
            dsrdtr=False,
            xonxoff=False,
            inter_byte_timeout=0.1,
        )
        self._open_event.set()

    async def flush_rx(self, drain_s: float = 0.2) -> None:
        """Discard all bytes currently in (or arriving into) the OS RX buffer.

        Call this AFTER sending a soft reset so that:
        1. Any inference the HLS engine had in flight at power-on or between runs
           is allowed to serialize through the UART TX (takes ≤87 µs per byte at
           115200 baud); drain_s=200 ms is ample margin.
        2. All those bytes are then atomically discarded before the real test
           epochs start.

        This prevents a stale DUT output byte from entering the scoreboard's
        dut_tx_fifo before any metadata is queued, which would cause the
        scoreboard to spin on metadata_underflows and then compare the stale byte
        against the wrong epoch.
        """
        await asyncio.sleep(drain_s)
        try:
            self.writer.transport.serial.reset_input_buffer()
        except Exception:
            pass

    async def wait_until_open(self) -> None:
        """Block until serial port is open."""
        await self._open_event.wait()

    async def close(self) -> None:
        """Close serial port connection."""
        if self.writer is None:
            return
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except AttributeError:
            pass
        self.reader = None
        self.writer = None
        self._open_event.clear()

    async def write_bytes(self, payload: bytes) -> None:
        """Write raw bytes to serial port."""
        await self.wait_until_open()
        if self.writer is None:
            raise RuntimeError("Serial writer is not available")
        self.writer.write(payload)
        await self.writer.drain()

    async def write_packet(self, packet_16b: int) -> None:
        """Write 16-bit packet as 2 bytes (LSB first)."""
        byte0 = packet_16b & 0xFF
        byte1 = (packet_16b >> 8) & 0xFF
        await self.write_bytes(bytes((byte0, byte1)))

    async def read_rx_byte(self) -> int:
        """Read one byte from serial port."""
        await self.wait_until_open()
        if self.reader is None:
            raise RuntimeError("Serial reader is not available")
        raw = await self.reader.read(1)
        if not raw:
            raise RuntimeError("Serial stream returned EOF")
        return raw[0] & 0xFF
