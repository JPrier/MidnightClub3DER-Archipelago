"""Dealer/showroom state probes.

These helpers are deliberately labeled as probes. The authoritative vehicle
lock source is not mapped yet, so consumers must not present these values as
confirmed lock state unless a probe has been proven.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .game import MC3Game


@dataclass(frozen=True)
class DealerProbeRow:
    addr: int
    current: int
    matches: tuple[str, ...]
    groups: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class DealerLockState:
    mapped: bool
    source: str


@dataclass(frozen=True)
class DealerRowProbe:
    index: int
    row_addr: int
    vehicle_id: str
    values: tuple[int, ...]


@dataclass(frozen=True)
class DealerRowsSnapshot:
    rows: tuple[DealerRowProbe, ...]
    source: str
    table_addr: int | None
    warnings: tuple[str, ...] = ()


DEALER_ROW_TABLE = 0x01B26910
DEALER_ROW_SIZE = 0x10
DEALER_ROW_MAX_ROWS = 64
DEALER_ROW_SCAN_RANGES = (
    (0x01A00000, 0x01D00000),
)

# Observed row-indexed byte arrays. These are useful for monitoring and
# candidate tests, but they are not proven as the authoritative lock source.
DEALER_ROW_VALUE_ARRAYS = (0x007FFE0E, 0x008384E0)


def load_probe_report(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def rows_by_addr(rows: list[dict]) -> dict[int, dict]:
    return {int(row["addr"]): row for row in rows}


def read_lock_state() -> DealerLockState:
    return DealerLockState(mapped=False, source="unmapped")


def _valid_ptr(value: int) -> bool:
    return 0x00100000 <= value < 0x01FFFFC0


def _read_vehicle_id(game: "MC3Game", vehicle_ptr: int) -> str:
    try:
        return game.bridge.read_cstring(vehicle_ptr, 64)
    except Exception:
        return ""


def _read_dealer_rows_at(game: "MC3Game", table_addr: int) -> list[DealerRowProbe]:
    data = game.read(table_addr, DEALER_ROW_MAX_ROWS * DEALER_ROW_SIZE)
    rows: list[DealerRowProbe] = []
    for i in range(DEALER_ROW_MAX_ROWS):
        _, vehicle_ptr, _, _ = struct.unpack_from("<IIII", data, i * DEALER_ROW_SIZE)
        if not _valid_ptr(vehicle_ptr):
            continue
        vehicle_id = _read_vehicle_id(game, vehicle_ptr)
        if not vehicle_id.startswith("vp_"):
            continue
        values = tuple(game.read(base + i, 1)[0] for base in DEALER_ROW_VALUE_ARRAYS)
        rows.append(DealerRowProbe(i, table_addr + i * DEALER_ROW_SIZE, vehicle_id, values))
    return rows


def _find_dealer_row_table(game: "MC3Game") -> int | None:
    best_addr = None
    best_score = 0
    for lo, hi in DEALER_ROW_SCAN_RANGES:
        for base in range(lo, hi, 0x10000):
            data = game.read(base, min(0x10000, hi - base))
            for off in range(0, len(data) - DEALER_ROW_SIZE * 3, 4):
                score = 0
                for i in range(8):
                    row_off = off + i * DEALER_ROW_SIZE
                    if row_off + DEALER_ROW_SIZE > len(data):
                        break
                    vehicle_ptr = struct.unpack_from("<I", data, row_off + 4)[0]
                    if not _valid_ptr(vehicle_ptr):
                        continue
                    vehicle_id = _read_vehicle_id(game, vehicle_ptr)
                    if vehicle_id.startswith("vp_"):
                        score += 1
                if score > best_score:
                    best_score = score
                    best_addr = base + off
                    if score >= 6:
                        return best_addr
    return best_addr if best_score >= 3 else None


def read_dealer_rows(
    game: "MC3Game",
    table_addr: int | None = None,
    allow_scan: bool = False,
) -> DealerRowsSnapshot:
    if table_addr is not None:
        rows = _read_dealer_rows_at(game, table_addr)
        return DealerRowsSnapshot(tuple(rows), f"explicit:0x{table_addr:08X}", table_addr)

    rows = _read_dealer_rows_at(game, DEALER_ROW_TABLE)
    if rows:
        return DealerRowsSnapshot(tuple(rows), f"fixed:0x{DEALER_ROW_TABLE:08X}", DEALER_ROW_TABLE)

    if not allow_scan:
        return DealerRowsSnapshot(
            (),
            f"fixed:0x{DEALER_ROW_TABLE:08X}",
            DEALER_ROW_TABLE,
            ("fixed dealer row table had no rows; scan not requested",),
        )

    found_addr = _find_dealer_row_table(game)
    if found_addr is None:
        return DealerRowsSnapshot(
            (),
            "scan:not-found",
            None,
            ("dealer row table scan found no candidate table",),
        )
    rows = _read_dealer_rows_at(game, found_addr)
    return DealerRowsSnapshot(tuple(rows), f"scan:0x{found_addr:08X}", found_addr)


def read_probe_rows(game: "MC3Game", report: Path, addresses: list[int] | None = None) -> list[DealerProbeRow]:
    rows = load_probe_report(report)
    if addresses is None:
        selected = rows
    else:
        wanted = set(addresses)
        by_addr = rows_by_addr(rows)
        missing = sorted(wanted - set(by_addr))
        if missing:
            missing_text = ", ".join(f"0x{addr:08X}" for addr in missing)
            raise ValueError(f"addresses not found in report: {missing_text}")
        selected = [by_addr[addr] for addr in addresses]

    result: list[DealerProbeRow] = []
    for row in selected:
        addr = int(row["addr"])
        current = game.read_u32(addr)
        matches = tuple(name for name, value in row["values"].items() if int(value) == current)
        groups = {
            str(value): tuple(captures)
            for value, captures in row["groups"].items()
        }
        result.append(DealerProbeRow(addr=addr, current=current, matches=matches, groups=groups))
    return result


def write_values_from_report(
    game: "MC3Game",
    report: Path,
    source_capture: str,
    addresses: list[int],
    width: int,
) -> dict[int, bytes]:
    rows = rows_by_addr(load_probe_report(report))
    missing = sorted(set(addresses) - set(rows))
    if missing:
        missing_text = ", ".join(f"0x{addr:08X}" for addr in missing)
        raise ValueError(f"addresses not found in report: {missing_text}")

    originals: dict[int, bytes] = {}
    for addr in addresses:
        row = rows[addr]
        if source_capture not in row["values"]:
            raise ValueError(f"source capture {source_capture!r} not found for 0x{addr:08X}")
        value = int(row["values"][source_capture])
        originals[addr] = game.read(addr, width)
        game.write(addr, value.to_bytes(width, "little", signed=False))
    return originals


def restore_values(game: "MC3Game", originals: dict[int, bytes]):
    for addr, value in originals.items():
        game.write(addr, value)
