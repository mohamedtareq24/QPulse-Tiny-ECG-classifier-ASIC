"""
ADC JTAG transport for XSDB/AXI MMIO sample injection in HIL mode.
Writes 8-bit samples and valid signal to hardware registers via JTAG.
"""

import asyncio


class AdcJiagTransport:
    """XSDB-based MMIO transport for ADC sample injection."""

    def __init__(
        self,
        xsdb_path: str = "xsdb",
        jtag_target_idx: int = 6,
        sample_addr: int = 0x40000000,
        valid_addr: int = 0x40010000,
    ):
        self.xsdb_path = xsdb_path
        self.jtag_target_idx = jtag_target_idx
        self.sample_addr = sample_addr
        self.valid_addr = valid_addr
        self._proc = None
        self._session_open = False

    async def open(self) -> None:
        """Open XSDB session and select JTAG target."""
        if self._session_open:
            return

        try:
            self._proc = await asyncio.create_subprocess_exec(
                self.xsdb_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )

            # Write connect/targets directly to the pipe — _session_open is
            # still False here so we cannot use _send_command yet.
            self._proc.stdin.write(b"connect\n")
            await self._proc.stdin.drain()
            self._proc.stdin.write(f"targets {self.jtag_target_idx}\n".encode())
            await self._proc.stdin.drain()

            # After a hard reset hw_server needs time to rescan the JTAG chain
            # and reattach.  Block here so no mwr commands are queued until
            # XSDB is actually ready.
            await asyncio.sleep(4.0)

            self._session_open = True
        except Exception as e:
            self._session_open = False
            raise RuntimeError(f"Failed to open XSDB session: {e}")

    async def close(self) -> None:
        """Close XSDB session."""
        if not self._session_open or self._proc is None:
            return
        
        try:
            await self._send_command("exit")
        except Exception:
            pass
        finally:
            if self._proc is not None:
                try:
                    self._proc.stdin.close()
                    self._proc.terminate()
                    await asyncio.sleep(0.1)
                    if self._proc.returncode is None:
                        self._proc.kill()
                except Exception:
                    pass
            self._session_open = False
            self._proc = None

    async def _send_command(self, cmd: str) -> None:
        """Write a single Tcl command to the XSDB stdin pipe."""
        if not self._session_open or self._proc is None:
            raise RuntimeError("XSDB session not open")
        self._proc.stdin.write((cmd + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def write_sample(self, sample_8b: int) -> None:
        """Write 8-bit sample to data register (valid stays as-is)."""
        await self.open()
        await self._send_command(f"mwr 0x{self.sample_addr:08X} 0x{sample_8b & 0xFF:08X}")

    async def write_valid(self, valid_bit: int) -> None:
        """Write valid signal (1 or 0) to register."""
        await self.open()
        await self._send_command(f"mwr 0x{self.valid_addr:08X} 0x{1 if valid_bit else 0:08X}")
