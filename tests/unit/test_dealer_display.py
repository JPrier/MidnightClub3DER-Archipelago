"""Unit tests for the dealer-display probe reader (no emulator needed)."""

import struct

from mc3api.dealer_display import (
    RING_BASE,
    RING_RECS,
    REC_COUNT,
    REC_SIZE,
    SITE,
    TRAMP_ADDR,
    DisplayProbeRecord,
    DisplayProbeRing,
    encode_jal,
)


class FakeBridge:
    def __init__(self):
        self.mem = bytearray(0x02000000)

    def read(self, addr, size):
        return bytes(self.mem[addr:addr + size])

    def write(self, addr, data):
        self.mem[addr:addr + len(data)] = data
        return len(data)

    def read_u32(self, addr):
        return struct.unpack_from("<I", self.mem, addr)[0]

    def write_u32(self, addr, value):
        struct.pack_into("<I", self.mem, addr, value & 0xFFFFFFFF)

    def install(self):
        self.write_u32(SITE, encode_jal(TRAMP_ADDR))

    def push(self, index, f04, f08, submode):
        count = self.read_u32(RING_BASE) + 1
        head = (self.read_u32(RING_BASE + 4) + 1) % REC_COUNT
        self.write_u32(RING_BASE, count)
        self.write_u32(RING_BASE + 4, head)
        self.write(RING_RECS + head * REC_SIZE,
                   struct.pack("<4I", index, f04, f08, submode))


def test_not_installed():
    b = FakeBridge()
    ring = DisplayProbeRing(b)
    assert ring.installed() is False
    assert ring.call_count() == 0
    assert ring.recent() == []


def test_recent_newest_first():
    b = FakeBridge()
    b.install()
    ring = DisplayProbeRing(b)
    b.push(4, 0, 0, 25)     # is300
    b.push(69, 0, 0, 39)    # scion tC
    out = ring.recent({4: "vp_is300_04", 69: "vp_d_scion_tc_05"})
    assert out[0] == DisplayProbeRecord(69, "vp_d_scion_tc_05", 0, 0, 39)
    assert out[1] == DisplayProbeRecord(4, "vp_is300_04", 0, 0, 25)


def test_recent_unresolved_name_is_empty_string():
    b = FakeBridge()
    b.install()
    ring = DisplayProbeRing(b)
    b.push(7, 1, 2, 24)
    out = ring.recent({})   # no name map provided
    assert out[0].vehicle_name == ""
    assert out[0].vehicle_index == 7


def test_recent_caps_at_rec_count_on_burst():
    b = FakeBridge()
    b.install()
    ring = DisplayProbeRing(b)
    for i in range(REC_COUNT + 5):
        b.push(i, 0, 0, 0)
    out = ring.recent()
    assert len(out) == REC_COUNT
    assert out[0].vehicle_index == REC_COUNT + 4     # newest
