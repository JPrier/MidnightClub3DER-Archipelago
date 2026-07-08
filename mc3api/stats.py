"""Career stats catalog — the game's tagged stat registry.

The catalog (pointer at MAP.stats_catalog_ptr) is an ordered array of 16-byte
entries: [tag:4CC][index:u32][meta_ptr:u32][value:u32|f32], terminated by
uninitialized memory (0xCDCDCDCD fill).

Entries INSERT when a stat type first occurs (e.g. LOCg appears on the first
collectible pickup), shifting all later entries. Access is therefore
tag-scan only. See docs/stats_catalog.md for the differential evidence.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple


TERMINATOR = 0xCDCDCDCD
ENTRY_SIZE = 16
MAX_ENTRIES = 512


class TAGS:
    """Well-known catalog tags. Semantic name reads reversed (LOC -> 'COL')."""

    # Confirmed by differential proof
    COLLECTIBLES_CITY = "LOCc"     # index = city id (0=San Diego, 1, 2)
    COLLECTIBLES_TOTAL = "LOCg"
    TOURNAMENT_WINS = "UOTk"
    WINS_CAREER = "NIWk"
    WINS_GLOBAL = "NIWg"
    WINS_VEHICLE = "NIWv"          # index = vehicle id
    RACES_ENTERED = "RACk"
    CAREER_EARNINGS = "EC$k"
    SECOND_PLACES = "DN2k"
    THIRD_PLACES = "DR3k"
    ROUTE_BEST_TIME = "IT:r"       # index = stable route id, value = f32 seconds
    ROUTE_AVG_SPEED = "PSAr"       # index = stable route id, value = f32

    # High-confidence hypotheses (see docs/stats_catalog.md)
    PLAY_TIME_HOURS = "PThg"
    DISTANCE_KM_CITY = "SDkc"
    DISTANCE_KM_GLOBAL = "SDkg"
    DISTANCE_KM_VEHICLE = "TSDv"
    TOP_SPEED = "STvg"
    LONGEST_JUMP = "DJmg"


# Tags whose value field is a float
_FLOAT_TAGS = {
    TAGS.ROUTE_BEST_TIME, TAGS.ROUTE_AVG_SPEED, TAGS.PLAY_TIME_HOURS,
    TAGS.DISTANCE_KM_CITY, TAGS.DISTANCE_KM_GLOBAL, TAGS.DISTANCE_KM_VEHICLE,
    TAGS.TOP_SPEED, TAGS.LONGEST_JUMP, "TAsg", "TJsg", "EA%k", "GA%k", "FA%k",
}


@dataclass(frozen=True)
class StatEntry:
    tag: str          # 4-character tag as stored (e.g. 'UOTk')
    index: int        # entry index (city/route/vehicle id; 0 for scalars)
    meta_ptr: int     # game-internal descriptor pointer
    raw_value: int    # value as u32

    @property
    def value(self) -> float | int:
        if self.tag in _FLOAT_TAGS:
            return struct.unpack("<f", struct.pack("<I", self.raw_value))[0]
        return self.raw_value

    @property
    def key(self) -> Tuple[str, int]:
        return (self.tag, self.index)


def parse_catalog(raw: bytes) -> List[StatEntry]:
    """Parse raw catalog bytes into entries. Pure function — unit-testable.

    Stops at the 0xCDCDCDCD terminator or a non-ASCII tag.
    """
    entries: List[StatEntry] = []
    for i in range(0, min(len(raw), MAX_ENTRIES * ENTRY_SIZE), ENTRY_SIZE):
        if i + ENTRY_SIZE > len(raw):
            break
        tag_u32, idx, meta, val = struct.unpack_from("<4I", raw, i)
        if tag_u32 == TERMINATOR:
            break
        tag_bytes = raw[i:i + 4]
        if not all(0x20 <= b < 0x7F for b in tag_bytes):
            break
        entries.append(StatEntry(tag_bytes.decode("ascii"), idx, meta, val))
    return entries


class StatsCatalog:
    """Live view of the stats catalog. Re-reads memory on refresh()."""

    def __init__(self, bridge, memmap):
        self._bridge = bridge
        self._map = memmap
        self._entries: List[StatEntry] = []
        self.refresh()

    def refresh(self) -> "StatsCatalog":
        base = self._bridge.read_u32(self._map.stats_catalog_ptr)
        if not (0x00100000 < base < 0x02000000):
            self._entries = []
            return self
        raw = self._bridge.read(base, MAX_ENTRIES * ENTRY_SIZE)
        self._entries = parse_catalog(raw)
        return self

    # ── Access ───────────────────────────────────────────────────────────

    @property
    def entries(self) -> List[StatEntry]:
        return list(self._entries)

    def get(self, tag: str, index: int = 0) -> Optional[StatEntry]:
        for e in self._entries:
            if e.tag == tag and e.index == index:
                return e
        return None

    def first(self, tag: str) -> Optional[StatEntry]:
        """First entry with this tag, ignoring index. Use for scalar stats
        (some scalars carry a non-zero index field, e.g. LOCg's 0xffff0000)."""
        for e in self._entries:
            if e.tag == tag:
                return e
        return None

    def value(self, tag: str, index: int = 0, default=0):
        e = self.get(tag, index)
        return e.value if e is not None else default

    def scalar(self, tag: str, default=0):
        e = self.first(tag)
        return e.value if e is not None else default

    def all(self, tag: str) -> List[StatEntry]:
        return [e for e in self._entries if e.tag == tag]

    def as_dict(self) -> Dict[Tuple[str, int], int]:
        """Snapshot {(tag, index): raw_value} — used for diffing."""
        return {e.key: e.raw_value for e in self._entries}

    def __iter__(self) -> Iterator[StatEntry]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    # ── Semantic accessors (confirmed stats) ─────────────────────────────

    @property
    def collectibles_total(self) -> int:
        return self.scalar(TAGS.COLLECTIBLES_TOTAL)

    def collectibles_in_city(self, city: int) -> int:
        return self.value(TAGS.COLLECTIBLES_CITY, city)

    @property
    def tournament_wins(self) -> int:
        return self.scalar(TAGS.TOURNAMENT_WINS)

    @property
    def race_wins(self) -> int:
        return self.scalar(TAGS.WINS_CAREER)

    @property
    def races_entered(self) -> int:
        return self.scalar(TAGS.RACES_ENTERED)

    @property
    def career_earnings(self) -> int:
        return self.scalar(TAGS.CAREER_EARNINGS)

    @property
    def completed_route_ids(self) -> List[int]:
        """Stable route ids with a recorded best time — one per completed route."""
        return sorted(e.index for e in self.all(TAGS.ROUTE_BEST_TIME))

    def route_best_time(self, route_id: int) -> Optional[float]:
        e = self.get(TAGS.ROUTE_BEST_TIME, route_id)
        return e.value if e else None
