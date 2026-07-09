"""Reader for the dealer item-display probe. This module is the single
source of truth for its mailbox layout — tools/probe_dealer_display.py (which
builds and installs the trampoline) imports these constants rather than
redefining them.

The probe hooks the showroom's per-item display function (0x00329480) and is
strictly non-mutating: it re-derives the vehicle index the same way the
purchase deny gate does, reads the catalog's class/rank fields and the UI
screen submode, logs them to a ring, then replays the function's own first
instruction and jumps back in. Correlating these records against what's
actually shown on screen (Locked / price / Owned) is how the availability
predicate gets pinned down — see docs/DEALER_AVAILABILITY_HUNT.md.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List

SITE = 0x00329480
TRAMP_ADDR = 0x00720E00
RING_BASE = 0x00720D00
RING_RECS = 0x00720D10
REC_SIZE = 0x10
REC_COUNT = 8


def encode_jal(target: int) -> int:
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


@dataclass(frozen=True)
class DisplayProbeRecord:
    """One showroom item-display call, decoded."""
    vehicle_index: int
    vehicle_name: str        # "" if not in the current catalog snapshot
    class_field: int         # catalog entry +0x04
    rank_field: int          # catalog entry +0x08
    submode: int             # ctx+0x1B4 UI screen submode


class DisplayProbeRing:
    """Reads the display-probe ring. Unlike PurchaseRing this is a live
    "recent activity" view, not a drain-once event stream — the same items
    redisplay every frame while visible, so re-reading the same records is
    expected and useful for a live monitor."""

    def __init__(self, bridge):
        self._bridge = bridge

    def installed(self) -> bool:
        try:
            return self._bridge.read_u32(SITE) == encode_jal(TRAMP_ADDR)
        except Exception:
            return False

    def call_count(self) -> int:
        return self._bridge.read_u32(RING_BASE)

    def recent(self, vehicle_names: dict[int, str] | None = None) -> List[DisplayProbeRecord]:
        """Return up to REC_COUNT most-recent records, newest first."""
        names = vehicle_names or {}
        count = self._bridge.read_u32(RING_BASE)
        if count == 0:
            return []
        head = self._bridge.read_u32(RING_BASE + 4)
        n = min(count, REC_COUNT)
        out: List[DisplayProbeRecord] = []
        for k in range(n):
            slot = (head - k) % REC_COUNT
            rec = self._bridge.read(RING_RECS + slot * REC_SIZE, REC_SIZE)
            index, f04, f08, submode = struct.unpack("<4I", rec)
            out.append(DisplayProbeRecord(
                vehicle_index=index, vehicle_name=names.get(index, ""),
                class_field=f04, rank_field=f08, submode=submode))
        return out
