"""MC3Game — the top-level facade of the modding API."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import List, Optional

from .bridge import PCSX2Bridge
from .dealer import DealerLockState, DealerProbeRow, DealerRowsSnapshot
from .memmap import MAP, MemoryMap
from .stats import StatsCatalog
from .vehicles import Vehicle, read_vehicles


class MC3Game:
    """Live handle to a running MC3 game inside stock PCSX2.

    Usage:
        game = MC3Game.connect()
        game.money += 5000
        print(game.stats.tournament_wins)
        print(game.last_event_path)
    """

    def __init__(self, bridge: PCSX2Bridge, memmap: MemoryMap = MAP):
        self.bridge = bridge
        self.map = memmap
        self.stats = StatsCatalog(bridge, memmap)

    @classmethod
    def connect(cls, timeout: float = 30.0) -> "MC3Game":
        return cls(PCSX2Bridge.connect(timeout=timeout))

    def close(self):
        self.bridge.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── Wallet ───────────────────────────────────────────────────────────

    @property
    def money(self) -> int:
        return self.bridge.read_u32(self.map.money)

    @money.setter
    def money(self, value: int):
        self.bridge.write_u32(self.map.money, max(0, value))

    # ── Race state ───────────────────────────────────────────────────────

    @property
    def live_race_position(self) -> int:
        """1..6 while racing; meaning outside a race is undefined."""
        return self.bridge.read_u32(self.map.live_race_position)

    # ── Profile ──────────────────────────────────────────────────────────

    @property
    def profile_addr(self) -> int:
        return self.bridge.read_u32(self.map.profile_ptr)

    @property
    def last_event_path(self) -> str:
        """File path of the most recently played event ('' if none)."""
        prof = self.profile_addr
        if not (0x00100000 < prof < 0x02000000):
            return ""
        return self.bridge.read_cstring(prof + self.map.profile_last_event_path, 96)

    # ── Vehicles ─────────────────────────────────────────────────────────

    def vehicles(self) -> List[Vehicle]:
        return read_vehicles(self.bridge, self.map)

    # ── Dealer / showroom state ─────────────────────────────────────────

    def dealer_lock_state(self) -> DealerLockState:
        from .dealer import read_lock_state
        return read_lock_state()

    def dealer_rows(
        self,
        table_addr: int | None = None,
        allow_scan: bool = False,
    ) -> DealerRowsSnapshot:
        from .dealer import read_dealer_rows
        return read_dealer_rows(self, table_addr, allow_scan)

    def dealer_probe_rows(self, report: Path, addresses: list[int] | None = None) -> list[DealerProbeRow]:
        from .dealer import read_probe_rows
        return read_probe_rows(self, report, addresses)

    def write_dealer_probe_values(
        self,
        report: Path,
        source_capture: str,
        addresses: list[int],
        width: int = 4,
    ) -> dict[int, bytes]:
        from .dealer import write_values_from_report
        return write_values_from_report(self, report, source_capture, addresses, width)

    def restore_dealer_probe_values(self, originals: dict[int, bytes]):
        from .dealer import restore_values
        restore_values(self, originals)

    # ── Payload mailbox ──────────────────────────────────────────────────

    @property
    def payload_build_id(self) -> int:
        return self.bridge.read_u32(self.map.mailbox + self.map.mailbox_build_id)

    @property
    def payload_heartbeat(self) -> int:
        return self.bridge.read_u32(self.map.mailbox + self.map.mailbox_heartbeat_game)

    # ── Watching ─────────────────────────────────────────────────────────

    def watch(self, interval: float = 1.0):
        """Yield GameEvents forever (poll-based)."""
        from .events import GameWatcher
        return GameWatcher(self).poll_forever(interval)

    def watcher(self):
        from .events import GameWatcher
        return GameWatcher(self)

    # ── Low-level escape hatch for modders ───────────────────────────────

    def read(self, ee_addr: int, size: int) -> bytes:
        return self.bridge.read(ee_addr, size)

    def write(self, ee_addr: int, data: bytes):
        return self.bridge.write(ee_addr, data)

    def read_u32(self, ee_addr: int) -> int:
        return self.bridge.read_u32(ee_addr)

    def write_u32(self, ee_addr: int, value: int):
        self.bridge.write_u32(ee_addr, value)

    def hexdump(self, ee_addr: int, size: int = 64) -> str:
        data = self.read(ee_addr, size)
        lines = []
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            hx = " ".join(f"{b:02X}" for b in chunk)
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"  {ee_addr + i:08X}: {hx:<48s} {asc}")
        return "\n".join(lines)

    def __repr__(self):
        return f"MC3Game(pid={self.bridge.pid}, build={self.payload_build_id})"
