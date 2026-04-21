import asyncio

import serial_asyncio


class HilSerialTransport:
    def __init__(self):
        self.reader = None
        self.writer = None
        self._open_event = asyncio.Event()

    async def open(self, port: str, baud_rate: int) -> None:
        if self.writer is not None:
            return
        self.reader, self.writer = await serial_asyncio.open_serial_connection(
            url=port,
            baudrate=baud_rate,
        )
        self._open_event.set()

    async def wait_until_open(self) -> None:
        await self._open_event.wait()

    async def close(self) -> None:
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
        await self.wait_until_open()
        if self.writer is None:
            raise RuntimeError("Serial writer is not available")
        self.writer.write(payload)
        await self.writer.drain()

    async def write_packet(self, packet_16b: int) -> None:
        byte0 = packet_16b & 0xFF
        byte1 = (packet_16b >> 8) & 0xFF
        await self.write_bytes(bytes((byte0, byte1)))

    async def read_rx_byte(self) -> int:
        await self.wait_until_open()
        if self.reader is None:
            raise RuntimeError("Serial reader is not available")
        raw = await self.reader.read(1)
        if not raw:
            raise RuntimeError("Serial stream returned EOF")
        return raw[0] & 0xFF
