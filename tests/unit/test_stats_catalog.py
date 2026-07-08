"""Unit tests for mc3api.stats — pure parsing, no emulator required."""

import json
import struct
from pathlib import Path

import pytest

from mc3api.stats import ENTRY_SIZE, TAGS, TERMINATOR, StatEntry, parse_catalog


def entry(tag: bytes, index: int, meta: int, value: int) -> bytes:
    return tag + struct.pack("<3I", index, meta, value)


def f32(v: float) -> int:
    return struct.unpack("<I", struct.pack("<f", v))[0]


class TestParseCatalog:
    def test_empty(self):
        assert parse_catalog(b"") == []

    def test_terminator_stops_parse(self):
        raw = entry(b"LOCc", 0, 0x1A7E11, 1) + struct.pack("<4I", TERMINATOR, 0, 0, 0)
        entries = parse_catalog(raw)
        assert len(entries) == 1
        assert entries[0].tag == "LOCc"

    def test_non_ascii_tag_stops_parse(self):
        raw = entry(b"UOTk", 0, 0, 1) + entry(b"\x00\x01\x02\x03", 0, 0, 0)
        assert len(parse_catalog(raw)) == 1

    def test_entry_fields(self):
        raw = entry(b"UOTk", 0, 0x001A7E11, 1)
        e = parse_catalog(raw)[0]
        assert e.tag == "UOTk"
        assert e.index == 0
        assert e.meta_ptr == 0x001A7E11
        assert e.raw_value == 1
        assert e.value == 1

    def test_float_tags_decode_as_float(self):
        raw = entry(b"IT:r", 0x3E, 0, f32(61.011))
        e = parse_catalog(raw)[0]
        assert e.value == pytest.approx(61.011, abs=1e-3)

    def test_int_tags_stay_int(self):
        raw = entry(b"EC$k", 0, 0, 37880)
        assert parse_catalog(raw)[0].value == 37880

    def test_insert_shift_scenario(self):
        """Simulates the LOCg insertion observed s6->s13: same tags must be
        findable regardless of position."""
        before = (
            entry(b"LOCc", 0, 0, 0)
            + entry(b"NRBg", 0, 0, 3)
            + entry(b"UOTk", 0, 0, 0)
        )
        after = (
            entry(b"LOCc", 0, 0, 1)
            + entry(b"NRBg", 0, 0, 3)
            + entry(b"LOCg", 0xFFFF0000, 0x40000011, 1)  # inserted
            + entry(b"UOTk", 0, 0, 0)
        )
        tags_before = {e.tag for e in parse_catalog(before)}
        tags_after = {e.tag for e in parse_catalog(after)}
        assert tags_after - tags_before == {"LOCg"}
        # UOTk still found after the shift
        uot = [e for e in parse_catalog(after) if e.tag == "UOTk"]
        assert len(uot) == 1


DUMP_DIR = Path(__file__).resolve().parents[2]


def load_catalog_from_dump(name: str):
    path = DUMP_DIR / f"dump_{name}.json"
    if not path.exists():
        pytest.skip(f"{path.name} not present (local-only RE artifact)")
    chunks = json.loads(path.read_text())
    base = 0x007C0000
    raw = bytes.fromhex(chunks["007C0000"])
    off = 0x007C9EF0 - base
    return parse_catalog(raw[off:off + 16 * 512])


class TestAgainstRealDumps:
    """Regression against real memory dumps (skipped when dumps not present)."""

    def test_s13_has_collectible(self):
        entries = load_catalog_from_dump("s13")
        locc = [e for e in entries if e.tag == TAGS.COLLECTIBLES_CITY]
        assert locc[0].value == 1          # San Diego logo collected
        locg = [e for e in entries if e.tag == TAGS.COLLECTIBLES_TOTAL]
        assert locg and locg[0].raw_value == 1

    def test_s14_tournament_win(self):
        entries = load_catalog_from_dump("s14")
        uot = [e for e in entries if e.tag == TAGS.TOURNAMENT_WINS]
        assert uot and uot[0].value == 1

    def test_s6_no_tournament_no_collectible(self):
        entries = load_catalog_from_dump("s6")
        tags = {e.tag for e in entries}
        assert TAGS.COLLECTIBLES_TOTAL not in tags
        uot = [e for e in entries if e.tag == TAGS.TOURNAMENT_WINS]
        assert uot and uot[0].value == 0

    def test_s14_route_ids_superset_of_s6(self):
        r6 = {e.index for e in load_catalog_from_dump("s6") if e.tag == TAGS.ROUTE_BEST_TIME}
        r14 = {e.index for e in load_catalog_from_dump("s14") if e.tag == TAGS.ROUTE_BEST_TIME}
        assert r6 < r14
        assert r14 - r6 == {0x3E, 0x3F, 0x41}  # the tournament's three races
