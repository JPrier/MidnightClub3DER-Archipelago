"""Reader/writer for the dealer purchase hooks. This module is the single
source of truth for their mailbox layout — tools/hook_purchase.py (which
builds and installs the trampolines) imports these constants rather than
redefining them.

Detect ring:   the DETECT trampoline (0x00337A7C) appends one record per
               confirmed purchase. We drain new records since the last read
               and resolve each vehicle name from the record pointer.
Permit table:  the DENY trampoline (0x003378BC) reads permit_table[index] and
               an enforce flag; this module writes both from the AP allow-set.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Optional

# Mailbox layout
ENFORCE_FLAG = 0x007205FC
PERMIT_TABLE = 0x00720600
PERMIT_SIZE = 96
DETECT_SITE = 0x00337A7C
DETECT_TRAMP = 0x00720920
DENY_SITE = 0x003378BC
DENY_TRAMP = 0x00720A00
RING_BASE = 0x00720B00
RING_RECS = 0x00720B10
REC_SIZE = 0x10
REC_COUNT = 16
CARCFG_NAME_OFFSET = 0xDF


def encode_jal(target: int) -> int:
    """Encode a MIPS ``jal target`` word. Shared with tools/hook_purchase.py."""
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


@dataclass(frozen=True)
class VehiclePurchase:
    """One confirmed dealer purchase captured by the detect hook."""
    vehicle_name: str        # e.g. "vp_d_scion_tc_05" ("" if unresolvable)
    amount: int              # money spent (wallet_before - new_total)
    wallet_before: int
    ordinal: int             # 1-based purchase counter from the payload


class PurchaseRing:
    """Drains new purchase records from the detect ring.

    Tracks the payload's monotonic ``count`` so each purchase is yielded
    exactly once, even across the ring's 16-slot wraparound.
    """

    def __init__(self, bridge):
        self._bridge = bridge
        self._seen = self._current_count()

    def _current_count(self) -> int:
        try:
            return self._bridge.read_u32(RING_BASE)
        except Exception:
            return 0

    def installed(self) -> bool:
        try:
            return self._bridge.read_u32(DETECT_SITE) == encode_jal(DETECT_TRAMP)
        except Exception:
            return False

    def drain(self) -> List[VehiclePurchase]:
        """Return purchases recorded since the last drain (oldest first)."""
        count = self._current_count()
        if count <= self._seen:
            self._seen = count      # reset if the ring was re-zeroed
            return []
        new = min(count - self._seen, REC_COUNT)   # older ones overwritten
        out: List[VehiclePurchase] = []
        # records for ordinals (count-new+1 .. count); head points at `count`
        head = self._bridge.read_u32(RING_BASE + 4)
        for k in range(new, 0, -1):
            slot = (head - k + 1) % REC_COUNT
            rec = self._bridge.read(RING_RECS + slot * REC_SIZE, REC_SIZE)
            recptr, amount, wallet, ordn = struct.unpack("<4I", rec)
            out.append(VehiclePurchase(
                vehicle_name=self._resolve_name(recptr),
                amount=_s32(amount), wallet_before=wallet, ordinal=ordn))
        self._seen = count
        return out

    def _resolve_name(self, recptr: int) -> str:
        if not (0x00100000 < recptr < 0x02000000):
            return ""
        try:
            raw = self._bridge.read(recptr + CARCFG_NAME_OFFSET, 32)
            return raw.split(b"\x00")[0].decode("ascii", errors="replace")
        except Exception:
            return ""


def _s32(v: int) -> int:
    return v - (1 << 32) if v >= (1 << 31) else v


class PermitTable:
    """Writes the deny-gate permit table + enforce flag.

    ``apply`` is idempotent: it writes the full 96-byte table each call so the
    permit set always reflects exactly ``allowed_indices``.
    """

    def __init__(self, bridge):
        self._bridge = bridge

    def installed(self) -> bool:
        try:
            return self._bridge.read_u32(DENY_SITE) == encode_jal(DENY_TRAMP)
        except Exception:
            return False

    def apply(self, allowed_indices, enforce: bool):
        allowed = set(allowed_indices)
        table = bytes(1 if i in allowed else 0 for i in range(PERMIT_SIZE))
        self._bridge.write(PERMIT_TABLE, table)
        self._bridge.write(ENFORCE_FLAG, bytes([1 if enforce else 0]))

    def allow_all(self):
        self._bridge.write(PERMIT_TABLE, b"\x01" * PERMIT_SIZE)
        self._bridge.write(ENFORCE_FLAG, b"\x00")

    def read_enforce(self) -> bool:
        return self._bridge.read(ENFORCE_FLAG, 1)[0] != 0

    def denied_indices(self) -> List[int]:
        table = self._bridge.read(PERMIT_TABLE, PERMIT_SIZE)
        return [i for i, b in enumerate(table) if b == 0]
