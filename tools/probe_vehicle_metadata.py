"""Search live memory for vehicle metadata structures.

This is a reverse-engineering probe. It reads PCSX2/MC3 memory through mc3api
and writes JSON artifacts; it does not feed runtime logic or the live monitor.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import time
from pathlib import Path

from mc3api.game import MC3Game


ARTIFACT_DIR = Path("artifacts/vehicle_metadata")
DEFAULT_SCAN_RANGES = (
    (0x00100000, 0x02000000, "ee_ram"),
)
DEFAULT_VEHICLES = (
    "vp_is300_04",
    "vp_eclipse_04",
    "vp_jetta_03",
    "vp_srt4_04",
    "vp_golfr32_04",
    "vp_elise_04",
)
METADATA_NEEDLES = (
    "Lexus",
    "IS300",
    "Mitsubishi",
    "Eclipse",
    "Volkswagen",
    "Jetta",
    "Golf",
    "Dodge",
    "SRT",
    "Lotus",
    "Elise",
    "Class",
    "class",
    "Luxury",
    "Tuner",
    "Import",
    "Muscle",
    "Exotic",
    "SUV",
    "Bike",
)


def parse_range(value: str) -> tuple[int, int, str]:
    lo_s, hi_s = value.split("-", 1)
    lo = int(lo_s, 0)
    hi = int(hi_s, 0)
    return lo, hi, f"{lo:08X}_{hi:08X}"


def printable(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


def valid_ptr(value: int) -> bool:
    return 0x00100000 <= value < 0x01FFFFC0


def read_cstring_safe(game: MC3Game, addr: int, max_len: int = 96) -> str:
    if not valid_ptr(addr):
        return ""
    try:
        value = game.bridge.read_cstring(addr, max_len)
    except Exception:
        return ""
    if not value or not value.isprintable():
        return ""
    return value


def iter_chunks(game: MC3Game, ranges, chunk_size: int):
    for lo, hi, label in ranges:
        print(f"scan_range={label} 0x{lo:08X}-0x{hi:08X}", flush=True)
        for base in range(lo, hi, chunk_size):
            size = min(chunk_size, hi - base)
            try:
                yield label, base, game.read(base, size)
            except Exception as exc:
                print(f"read_failed=0x{base:08X} size=0x{size:X} error={exc}", flush=True)


def find_strings(game: MC3Game, needles: list[str], ranges, chunk_size: int):
    needle_bytes = [(needle, needle.encode("ascii", errors="ignore")) for needle in needles]
    hits = []
    for label, base, data in iter_chunks(game, ranges, chunk_size):
        low = data.lower()
        for needle, raw in needle_bytes:
            if not raw:
                continue
            pos = low.find(raw.lower())
            while pos >= 0:
                start = max(0, pos - 64)
                end = min(len(data), pos + len(raw) + 128)
                hits.append({
                    "needle": needle,
                    "addr": base + pos,
                    "range": label,
                    "context": printable(data[start:end]),
                })
                pos = low.find(raw.lower(), pos + 1)
    return hits


def find_pointer_refs(game: MC3Game, string_hits, ranges, chunk_size: int):
    targets = sorted({hit["addr"] for hit in string_hits if hit["needle"].startswith("vp_")})
    target_to_needles: dict[int, list[str]] = {}
    for hit in string_hits:
        if hit["addr"] in targets:
            target_to_needles.setdefault(hit["addr"], []).append(hit["needle"])

    patterns = [(target, struct.pack("<I", target)) for target in targets]
    refs = []
    for label, base, data in iter_chunks(game, ranges, chunk_size):
        for target, pattern in patterns:
            pos = data.find(pattern)
            while pos >= 0:
                refs.append({
                    "target": target,
                    "vehicle_ids": sorted(set(target_to_needles.get(target, []))),
                    "ref_addr": base + pos,
                    "range": label,
                })
                pos = data.find(pattern, pos + 1)
    return refs


def decode_window(game: MC3Game, ref_addr: int, before: int, size: int):
    start = max(0x00100000, ref_addr - before)
    data = game.read(start, size)
    dwords = []
    for off in range(0, len(data) - 3, 4):
        addr = start + off
        value = struct.unpack_from("<I", data, off)[0]
        fvalue = struct.unpack_from("<f", data, off)[0]
        entry = {"addr": addr, "offset_from_ref": addr - ref_addr, "u32": value}
        s = read_cstring_safe(game, value)
        if s:
            entry["ptr_string"] = s
        if math.isfinite(fvalue) and -10000.0 <= fvalue <= 10000.0 and abs(fvalue) > 0.000001:
            entry["float"] = fvalue
        if value <= 1000000:
            entry["small_int"] = value
        dwords.append(entry)
    return {
        "start": start,
        "size": len(data),
        "ascii": printable(data),
        "dwords": dwords,
    }


def cmd_scan(args) -> int:
    ranges = [parse_range(v) for v in args.range] if args.range else list(DEFAULT_SCAN_RANGES)
    vehicles = args.vehicle or list(DEFAULT_VEHICLES)
    needles = vehicles + list(METADATA_NEEDLES)
    out = ARTIFACT_DIR / f"metadata_scan_{int(time.time())}.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    with MC3Game.connect(timeout=10) as game:
        string_hits = find_strings(game, needles, ranges, args.chunk_size)
        pointer_refs = find_pointer_refs(game, string_hits, ranges, args.chunk_size)
        decoded = []
        for ref in pointer_refs[:args.decode_limit]:
            decoded.append({
                **ref,
                "windows": [
                    decode_window(game, ref["ref_addr"], before, args.window_size)
                    for before in args.window_before
                ],
            })

    result = {
        "ranges": [{"start": lo, "end": hi, "label": label} for lo, hi, label in ranges],
        "vehicles": vehicles,
        "string_hits": string_hits,
        "pointer_refs": pointer_refs,
        "decoded_refs": decoded,
    }
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    print(f"string_hits={len(string_hits)} pointer_refs={len(pointer_refs)} decoded_refs={len(decoded)}")
    for hit in string_hits[:args.limit]:
        print(f"str 0x{hit['addr']:08X} {hit['needle']} {hit['context'][:120]}")
    for ref in pointer_refs[:args.limit]:
        ids = ",".join(ref["vehicle_ids"])
        print(f"ref 0x{ref['ref_addr']:08X} -> 0x{ref['target']:08X} {ids}")
    return 0


def cmd_around(args) -> int:
    with MC3Game.connect(timeout=10) as game:
        window = decode_window(game, args.addr, args.before, args.size)
    print(f"window_start=0x{window['start']:08X} size=0x{window['size']:X}")
    print(window["ascii"])
    for entry in window["dwords"]:
        parts = [f"0x{entry['addr']:08X}", f"rel={entry['offset_from_ref']:+d}", f"u32={entry['u32']}"]
        if "small_int" in entry:
            parts.append(f"small={entry['small_int']}")
        if "float" in entry:
            parts.append(f"float={entry['float']:.4g}")
        if "ptr_string" in entry:
            parts.append(f"ptr='{entry['ptr_string']}'")
        print("  " + " ".join(parts))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Probe live vehicle metadata structures")
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan")
    scan.add_argument("--vehicle", action="append", default=[])
    scan.add_argument("--range", action="append", default=[],
                      help="scan range like 0x00100000-0x02000000")
    scan.add_argument("--chunk-size", type=lambda v: int(v, 0), default=0x100000)
    scan.add_argument("--limit", type=int, default=40)
    scan.add_argument("--decode-limit", type=int, default=80)
    scan.add_argument("--window-before", action="append", type=lambda v: int(v, 0),
                      default=[0, 4, 0x10, 0x54])
    scan.add_argument("--window-size", type=lambda v: int(v, 0), default=0x100)
    scan.set_defaults(func=cmd_scan)

    around = sub.add_parser("around")
    around.add_argument("addr", type=lambda v: int(v, 0))
    around.add_argument("--before", type=lambda v: int(v, 0), default=0x40)
    around.add_argument("--size", type=lambda v: int(v, 0), default=0x140)
    around.set_defaults(func=cmd_around)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
