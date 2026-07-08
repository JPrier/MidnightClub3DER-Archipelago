r"""Capture and diff live dealer-selection memory.

Use this when the dealer/showroom is open and the cursor is on a known vehicle.
The goal is to compare an unlocked selection against a locked selection and
find the real UI/purchase decision fields.

Example:

  # Put cursor on IS300 or another purchasable car first.
  python tools\map_vehicle_selection.py capture unlocked_is300

  # Move cursor to a locked car, then capture again.
  python tools\map_vehicle_selection.py capture locked_cobalt

  python tools\map_vehicle_selection.py diff unlocked_is300 locked_cobalt
  python tools\map_vehicle_selection.py ndiff unlocked_is300 locked_cobalt another_capture
  python tools\map_vehicle_selection.py ndiff un-tc un-eclipse lo-elise --prefix-groups --group-split-only
  python tools\map_vehicle_selection.py ndiff un-tc lo-elise --group available=un-tc --group locked=lo-elise --group-split-only
  python tools\map_vehicle_selection.py live-from-report artifacts\...\ndiff_...json 0x01C465E4
  python tools\map_vehicle_selection.py pulse-from-report artifacts\...\ndiff_...json un-tc 0x01C465E4 --seconds 8
  python tools\map_vehicle_selection.py strings
"""

from __future__ import annotations

import argparse
import json
import struct
import time
from pathlib import Path

from mc3api.game import MC3Game


ARTIFACT_DIR = Path("artifacts/vehicle_lock_mapping/selection_snapshots")
DEFAULT_RANGES = (
    (0x00600000, 0x00900000, "core_6_9"),
    (0x01A00000, 0x01D00000, "ui_1a_1d"),
)
STRING_NEEDLES = (
    b"Buy",
    b"buy",
    b"Purchase",
    b"purchase",
    b"Test Drive",
    b"ShowRoomPrice",
    b"Locked",
    b"locked",
    b"vp_is300_04",
    b"vp_d_cobalt_05",
    b"vp_montecarlo_78",
    b"vp_srt4_04",
    b"vp_jetta_03",
)


def parse_range(value: str) -> tuple[int, int, str]:
    lo_s, hi_s = value.split("-", 1)
    lo = int(lo_s, 16)
    hi = int(hi_s, 16)
    return lo, hi, f"{lo:08X}_{hi:08X}"


def parse_int(value: str) -> int:
    return int(value, 0)


def snapshot_dir(name: str) -> Path:
    return ARTIFACT_DIR / name


def chunk_path(out: Path, base: int) -> Path:
    return out / f"{base:08X}.bin"


def capture_once(game: MC3Game, name: str, ranges: list[tuple[int, int, str]]) -> Path:
    out = snapshot_dir(name)
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "name": name,
        "timestamp": time.time(),
        "ranges": [{"start": lo, "end": hi, "label": label} for lo, hi, label in ranges],
        "money": game.money,
        "last_event_path": game.last_event_path,
        "payload_build_id": game.payload_build_id,
    }
    for lo, hi, _ in ranges:
        for base in range(lo, hi, 0x10000):
            chunk_path(out, base).write_bytes(game.read(base, min(0x10000, hi - base)))
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out


def capture(name: str, ranges: list[tuple[int, int, str]], count: int = 1, pause: float = 0.0):
    game = MC3Game.connect(timeout=10)
    try:
        for i in range(count):
            suffix = f"_{i + 1:02d}" if count > 1 else ""
            capture_name = f"{name}{suffix}"
            out = capture_once(game, capture_name, ranges)
            print(f"captured {capture_name} -> {out}")
            if i + 1 < count and pause > 0:
                time.sleep(pause)
    finally:
        game.close()


def read_chunk(name: str, base: int) -> bytes:
    path = chunk_path(snapshot_dir(name), base)
    return path.read_bytes() if path.exists() else b""


def iter_snapshot_bases(name: str) -> list[int]:
    out = snapshot_dir(name)
    return sorted(int(path.stem, 16) for path in out.glob("*.bin"))


def diff(before: str, after: str, limit: int):
    bases = sorted(set(iter_snapshot_bases(before)) & set(iter_snapshot_bases(after)))
    rows = []
    for base in bases:
        a = read_chunk(before, base)
        b = read_chunk(after, base)
        if len(a) != len(b):
            continue
        for off in range(0, len(a), 4):
            old = struct.unpack_from("<I", a, off)[0]
            new = struct.unpack_from("<I", b, off)[0]
            if old == new:
                continue
            addr = base + off
            score = 0
            if old < 256 and new < 256:
                score += 5
            if (old, new) in ((0, 1), (1, 0), (0, 2), (2, 0), (1, 2), (2, 1)):
                score += 5
            if abs((new & 0xFFFFFFFF) - (old & 0xFFFFFFFF)) <= 20:
                score += 2
            if 0x01A00000 <= addr < 0x01D00000:
                score += 2
            if 0x00600000 <= addr < 0x00900000:
                score += 1
            if score <= 0:
                continue
            s = max(0, off - 32)
            e = min(len(a), off + 64)
            rows.append({
                "addr": addr,
                "old": old,
                "new": new,
                "score": score,
                "ascii_old": printable(a[s:e]),
                "ascii_new": printable(b[s:e]),
            })
    rows.sort(key=lambda row: (-row["score"], row["addr"]))
    out = ARTIFACT_DIR / f"diff_{before}_to_{after}.json"
    out.write_text(json.dumps(rows[:5000], indent=2), encoding="utf-8")
    print(f"wrote {out}; candidates={len(rows)}")
    for row in rows[:limit]:
        print(
            f"0x{row['addr']:08X} {row['old']} -> {row['new']} "
            f"score={row['score']} {row['ascii_new'][:72]}"
        )


def prefix_groups(names: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for name in names:
        prefix = name.split("-", 1)[0]
        groups.setdefault(prefix, []).append(name)
    return {prefix: captures for prefix, captures in groups.items() if len(captures) >= 1}


def parse_group(value: str) -> tuple[str, list[str]]:
    label, captures = value.split("=", 1)
    names = [name.strip() for name in captures.split(",") if name.strip()]
    if not label or not names:
        raise argparse.ArgumentTypeError("group must look like label=capture1,capture2")
    return label, names


def group_split(values: dict[str, int], groups: dict[str, list[str]]) -> bool:
    if len(groups) < 2:
        return False

    group_values = []
    for captures in groups.values():
        unique = {values[name] for name in captures}
        if len(unique) != 1:
            return False
        group_values.append(next(iter(unique)))
    return len(set(group_values)) > 1


def ndiff(
    names: list[str],
    limit: int,
    top: int,
    use_prefix_groups: bool = False,
    group_split_only: bool = False,
    explicit_groups: list[tuple[str, list[str]]] | None = None,
):
    groups_by_label = dict(explicit_groups or [])
    if use_prefix_groups:
        groups_by_label.update(prefix_groups(names))
    unknown = sorted({capture for captures in groups_by_label.values() for capture in captures} - set(names))
    if unknown:
        raise SystemExit(f"group contains captures not in ndiff input: {', '.join(unknown)}")

    bases = set(iter_snapshot_bases(names[0]))
    for name in names[1:]:
        bases &= set(iter_snapshot_bases(name))

    rows = []
    total_differing = 0
    for base in sorted(bases):
        chunks = [read_chunk(name, base) for name in names]
        if any(len(chunk) != len(chunks[0]) for chunk in chunks):
            continue

        for off in range(0, len(chunks[0]), 4):
            values = [struct.unpack_from("<I", chunk, off)[0] for chunk in chunks]
            unique = sorted(set(values))
            if len(unique) <= 1:
                continue

            total_differing += 1
            addr = base + off
            values_by_name = dict(zip(names, values))
            is_group_split = group_split(values_by_name, groups_by_label)
            if group_split_only and not is_group_split:
                continue

            score = 0
            if all(v < 256 for v in values):
                score += 5
            if set(unique) <= {0, 1}:
                score += 8
            elif set(unique) <= {0, 1, 2}:
                score += 6
            if max(unique) - min(unique) <= 20:
                score += 2
            if 0x01A00000 <= addr < 0x01D00000:
                score += 2
            if 0x00600000 <= addr < 0x00900000:
                score += 1
            if is_group_split:
                score += 30

            groups: dict[int, list[str]] = {}
            for name, value in zip(names, values):
                groups.setdefault(value, []).append(name)

            s = max(0, off - 32)
            e = min(len(chunks[0]), off + 64)
            rows.append({
                "addr": addr,
                "score": score,
                "values": values_by_name,
                "groups": {str(k): v for k, v in sorted(groups.items())},
                "prefix_group_split": is_group_split,
                "ascii": {name: printable(chunk[s:e]) for name, chunk in zip(names, chunks)},
            })

    rows.sort(key=lambda row: (-row["score"], not row["prefix_group_split"], len(row["groups"]), row["addr"]))
    suffix = ""
    if use_prefix_groups:
        suffix += "_prefix-groups"
    if explicit_groups:
        suffix += "_explicit-groups"
    if group_split_only:
        suffix += "_group-split-only"
    out = ARTIFACT_DIR / f"ndiff_{'_'.join(names)}{suffix}.json"
    out.write_text(json.dumps(rows[:top], indent=2), encoding="utf-8")
    if groups_by_label:
        group_text = ", ".join(f"{label}=({', '.join(captures)})" for label, captures in groups_by_label.items())
        print(f"groups: {group_text}")
    print(f"wrote {out}; differing_addresses={total_differing}; reported_addresses={len(rows)}")
    for row in rows[:limit]:
        group_text = "; ".join(
            f"{value}: {', '.join(captures)}"
            for value, captures in row["groups"].items()
        )
        print(f"0x{row['addr']:08X} score={row['score']} {group_text}")


def printable(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


def strings():
    game = MC3Game.connect(timeout=10)
    try:
        for lo, hi, label in DEFAULT_RANGES:
            print(f"\n[{label}]")
            for base in range(lo, hi, 0x100000):
                data = game.read(base, min(0x100000, hi - base))
                low = data.lower()
                for needle in STRING_NEEDLES:
                    pos = low.find(needle.lower())
                    while pos >= 0:
                        addr = base + pos
                        start = max(0, pos - 72)
                        end = min(len(data), pos + 160)
                        print(f"0x{addr:08X} {needle.decode(errors='replace')}: {printable(data[start:end])}")
                        pos = low.find(needle.lower(), pos + 1)
    finally:
        game.close()


def pulse_from_report(report: Path, source: str, addresses: list[int], seconds: float, width: int):
    game = MC3Game.connect(timeout=10)
    originals: dict[int, bytes] = {}
    try:
        before_rows = game.dealer_probe_rows(report, addresses)
        originals = game.write_dealer_probe_values(report, source, addresses, width)
        after_rows = game.dealer_probe_rows(report, addresses)
        print("before:")
        print_probe_rows(before_rows)
        print("after write:")
        print_probe_rows(after_rows)

        print(f"holding for {seconds:g}s; watch the dealer screen now")
        time.sleep(seconds)
    finally:
        game.restore_dealer_probe_values(originals)
        if originals:
            restored_rows = game.dealer_probe_rows(report, addresses)
            print("after restore:")
            print_probe_rows(restored_rows)
        game.close()
    print("restored")


def print_probe_rows(rows):
    for row in rows:
        group_text = "; ".join(
            f"{value}: {', '.join(captures)}"
            for value, captures in row.groups.items()
        )
        matches = ", ".join(row.matches) if row.matches else "-"
        print(f"  0x{row.addr:08X}: current={row.current} matches={matches} report=({group_text})")


def live_from_report(report: Path, addresses: list[int]):
    game = MC3Game.connect(timeout=10)
    try:
        print_probe_rows(game.dealer_probe_rows(report, addresses))
    finally:
        game.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Capture/diff dealer selection memory")
    sub = parser.add_subparsers(dest="cmd", required=True)

    capture_p = sub.add_parser("capture")
    capture_p.add_argument("name")
    capture_p.add_argument("--count", type=int, default=1,
                           help="number of sequential captures to take (default 1)")
    capture_p.add_argument("--pause", type=float, default=0.0,
                           help="seconds to wait between captures")
    capture_p.add_argument(
        "--range",
        action="append",
        default=[],
        help="extra/override range like 0x00600000-0x00900000",
    )

    diff_p = sub.add_parser("diff")
    diff_p.add_argument("before")
    diff_p.add_argument("after")
    diff_p.add_argument("--limit", type=int, default=80)

    ndiff_p = sub.add_parser("ndiff")
    ndiff_p.add_argument("names", nargs="+")
    ndiff_p.add_argument("--limit", type=int, default=80)
    ndiff_p.add_argument("--top", type=int, default=10000,
                         help="number of candidate rows to write to JSON")
    ndiff_p.add_argument(
        "--prefix-groups",
        action="store_true",
        help="group captures by name prefix before '-' and boost consistent splits",
    )
    ndiff_p.add_argument(
        "--group",
        action="append",
        type=parse_group,
        default=[],
        help="explicit group like available=un-tc,un-eclipse; repeat for locked=...",
    )
    ndiff_p.add_argument(
        "--group-split-only",
        action="store_true",
        help="only report rows where every prefix group is internally equal and groups differ",
    )

    sub.add_parser("strings")

    pulse_report_p = sub.add_parser(
        "pulse-from-report",
        help="temporarily write values from one capture in an ndiff JSON report",
    )
    pulse_report_p.add_argument("report", type=Path)
    pulse_report_p.add_argument("source_capture")
    pulse_report_p.add_argument("addresses", nargs="+", type=parse_int)
    pulse_report_p.add_argument("--seconds", type=float, default=8.0)
    pulse_report_p.add_argument("--width", type=int, choices=(1, 2, 4), default=4)

    live_report_p = sub.add_parser(
        "live-from-report",
        help="read live values for addresses listed in an ndiff JSON report",
    )
    live_report_p.add_argument("report", type=Path)
    live_report_p.add_argument("addresses", nargs="+", type=parse_int)

    args = parser.parse_args(argv)
    if args.cmd == "capture":
        ranges = [parse_range(v) for v in args.range] if args.range else list(DEFAULT_RANGES)
        capture(args.name, ranges, args.count, args.pause)
    elif args.cmd == "diff":
        diff(args.before, args.after, args.limit)
    elif args.cmd == "ndiff":
        if len(args.names) < 2:
            raise SystemExit("ndiff requires at least two capture names")
        ndiff(args.names, args.limit, args.top, args.prefix_groups, args.group_split_only, args.group)
    elif args.cmd == "strings":
        strings()
    elif args.cmd == "pulse-from-report":
        pulse_from_report(args.report, args.source_capture, args.addresses, args.seconds, args.width)
    elif args.cmd == "live-from-report":
        live_from_report(args.report, args.addresses)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
