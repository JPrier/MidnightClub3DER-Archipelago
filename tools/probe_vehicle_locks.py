"""Probe observed dealer row values in live PCSX2 memory.

This is an RE tool. It does not know whether any value means locked or
unlocked; it only reads and writes the same row-indexed bytes exposed by the
mc3api dealer API.
"""

from __future__ import annotations

import argparse
import time

from mc3api.dealer import DEALER_ROW_VALUE_ARRAYS
from mc3api.game import MC3Game


def find_row(rows, vehicle_id: str):
    needle = vehicle_id.lower()
    for row in rows:
        if row.vehicle_id.lower() == needle:
            return row
    matches = [row for row in rows if needle in row.vehicle_id.lower()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        names = ", ".join(row.vehicle_id for row in matches)
        raise SystemExit(f"ambiguous vehicle {vehicle_id!r}; matches: {names}")
    raise SystemExit(f"vehicle {vehicle_id!r} not found in dealer row table")


def print_rows(rows):
    print("idx  values  vehicle")
    print("---  ------  -------")
    for row in rows:
        values = "/".join(str(value) for value in row.values)
        print(f"{row.index:>3}  {values:<6}  {row.vehicle_id}")


def write_row_values(game: MC3Game, row, values: list[int]) -> dict[int, bytes]:
    if len(values) == 1:
        values = values * len(DEALER_ROW_VALUE_ARRAYS)
    if len(values) != len(DEALER_ROW_VALUE_ARRAYS):
        raise SystemExit(f"expected 1 or {len(DEALER_ROW_VALUE_ARRAYS)} values")

    originals: dict[int, bytes] = {}
    for base, value in zip(DEALER_ROW_VALUE_ARRAYS, values):
        addr = base + row.index
        originals[addr] = game.read(addr, 1)
        game.write(addr, bytes([value & 0xFF]))
    return originals


def restore(game: MC3Game, originals: dict[int, bytes]):
    for addr, value in originals.items():
        game.write(addr, value)


def parse_values(value: str) -> list[int]:
    return [int(part, 0) for part in value.split("/")]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Probe live MC3 dealer row bytes")
    sub = parser.add_subparsers(dest="cmd", required=True)
    parser.add_argument("--table", type=lambda value: int(value, 0),
                        help="explicit dealer row table address")
    parser.add_argument("--scan-table", action="store_true",
                        help="scan for row table if the fixed address has no rows")

    sub.add_parser("rows", help="list current dealer rows and observed values")

    set_p = sub.add_parser("set-value", help="set observed row byte values")
    set_p.add_argument("vehicle")
    set_p.add_argument("values", type=parse_values, help="single value or slash pair, e.g. 1 or 1/0")

    pulse_p = sub.add_parser("pulse-value", help="temporarily set observed row byte values, then restore")
    pulse_p.add_argument("vehicle")
    pulse_p.add_argument("values", type=parse_values, help="single value or slash pair, e.g. 1 or 1/0")
    pulse_p.add_argument("--seconds", type=float, default=10.0)

    args = parser.parse_args(argv)

    game = MC3Game.connect(timeout=10)
    try:
        snapshot = game.dealer_rows(args.table, args.scan_table)
        print(f"row_source={snapshot.source} rows={len(snapshot.rows)}")
        for warning in snapshot.warnings:
            print(f"warning={warning}")
        rows = list(snapshot.rows)
        if args.cmd == "rows":
            print_rows(rows)
            return 0

        row = find_row(rows, args.vehicle)
        originals = write_row_values(game, row, args.values)
        after = find_row(list(game.dealer_rows(args.table, args.scan_table).rows), row.vehicle_id)
        print(f"{row.vehicle_id}: {row.values} -> {after.values}")

        if args.cmd == "pulse-value":
            print(f"holding for {args.seconds:g}s; watch the dealer screen now")
            time.sleep(args.seconds)
            restore(game, originals)
            restored = find_row(list(game.dealer_rows(args.table, args.scan_table).rows), row.vehicle_id)
            print(f"restored: {restored.values}")
        return 0
    finally:
        game.close()


if __name__ == "__main__":
    raise SystemExit(main())
