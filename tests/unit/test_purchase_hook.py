"""Unit tests for the dealer purchase hook readers (no emulator needed)."""

import struct

from mc3api.purchase_hook import (
    DETECT_SITE,
    DETECT_TRAMP,
    ENFORCE_FLAG,
    PERMIT_SIZE,
    PERMIT_TABLE,
    RING_BASE,
    RING_RECS,
    REC_COUNT,
    REC_SIZE,
    PermitTable,
    PurchaseRing,
    VehiclePurchase,
)


class FakeBridge:
    """Flat little-endian EE memory backed by a dict of address->byte."""

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

    # helpers for the test
    def install_detect(self):
        jal = 0x0C000000 | ((DETECT_TRAMP >> 2) & 0x03FFFFFF)
        self.write_u32(DETECT_SITE, jal)

    def push_purchase(self, recptr, amount, wallet, name):
        count = self.read_u32(RING_BASE)
        head = self.read_u32(RING_BASE + 4)
        count += 1
        head = (head + 1) % REC_COUNT
        self.write_u32(RING_BASE, count)
        self.write_u32(RING_BASE + 4, head)
        rec = struct.pack("<4I", recptr, amount & 0xFFFFFFFF, wallet, count)
        self.write(RING_RECS + head * REC_SIZE, rec)
        # vehicle name c-string at recptr + 0xDF
        self.write(recptr + 0xDF, name.encode() + b"\x00")


def test_ring_not_installed():
    b = FakeBridge()
    ring = PurchaseRing(b)
    assert ring.installed() is False
    assert ring.drain() == []


def test_ring_drains_new_purchases_in_order():
    b = FakeBridge()
    b.install_detect()
    ring = PurchaseRing(b)          # snapshots current count (0)
    assert ring.installed()
    b.push_purchase(0x007D0000, 5000, 100000, "vp_d_scion_tc_05")
    b.push_purchase(0x007D0400, 12000, 95000, "vp_is300_04")
    out = ring.drain()
    assert [p.vehicle_name for p in out] == ["vp_d_scion_tc_05", "vp_is300_04"]
    assert out[0] == VehiclePurchase("vp_d_scion_tc_05", 5000, 100000, 1)
    assert out[1].amount == 12000 and out[1].ordinal == 2
    # draining again yields nothing new
    assert ring.drain() == []


def test_ring_negative_amount_is_signed():
    b = FakeBridge()
    b.install_detect()
    ring = PurchaseRing(b)
    b.push_purchase(0x007D0000, -250 & 0xFFFFFFFF, 100000, "vp_refund")
    out = ring.drain()
    assert out[0].amount == -250


def test_ring_reset_reprimes():
    b = FakeBridge()
    b.install_detect()
    ring = PurchaseRing(b)
    b.push_purchase(0x007D0000, 5000, 100000, "vp_a")
    ring.drain()
    # payload re-zeroed the ring (reinstall) -> count goes back below seen
    b.write_u32(RING_BASE, 0)
    assert ring.drain() == []
    # new purchase after reset is picked up
    b.push_purchase(0x007D0000, 700, 99000, "vp_b")
    out = ring.drain()
    assert [p.vehicle_name for p in out] == ["vp_b"]


def test_ring_only_keeps_last_16_on_burst():
    b = FakeBridge()
    b.install_detect()
    ring = PurchaseRing(b)
    for i in range(20):
        b.push_purchase(0x007D0000 + i * 0x400, 100 + i, 100000, f"vp_{i:02d}")
    out = ring.drain()
    assert len(out) == REC_COUNT          # older overwritten
    assert out[-1].ordinal == 20          # newest preserved


def test_permit_table_apply_encodes_allow_set():
    b = FakeBridge()
    PermitTable(b).apply({0, 23, 93}, enforce=True)
    table = b.read(PERMIT_TABLE, PERMIT_SIZE)
    assert table[0] == 1 and table[23] == 1 and table[93] == 1
    assert table[1] == 0 and table[50] == 0
    assert b.read(ENFORCE_FLAG, 1)[0] == 1
    assert PermitTable(b).denied_indices() == [
        i for i in range(PERMIT_SIZE) if i not in (0, 23, 93)]


def test_permit_allow_all_clears_enforce():
    b = FakeBridge()
    PermitTable(b).apply({5}, enforce=True)
    PermitTable(b).allow_all()
    assert b.read(ENFORCE_FLAG, 1)[0] == 0
    assert PermitTable(b).denied_indices() == []


def test_check_mapper_maps_vehicle_purchase():
    from mc3api.events import VehiclePurchased
    from client.mc3ap.adapters.pcsx2.check_mapper import map_event_to_checks

    ev = VehiclePurchased(0.0, vehicle_name="vp_is300_04", amount=12000,
                          wallet_before=95000, ordinal=1)
    checks = map_event_to_checks(ev)
    assert len(checks) == 1
    assert checks[0].location_name == "Vehicle Purchased: vp_is300_04"
    assert checks[0].source == "purchase"


def test_check_mapper_skips_unresolved_purchase():
    from mc3api.events import VehiclePurchased
    from client.mc3ap.adapters.pcsx2.check_mapper import map_event_to_checks

    ev = VehiclePurchased(0.0, vehicle_name="", amount=0,
                          wallet_before=0, ordinal=1)
    assert map_event_to_checks(ev) == []


def _load_hook_tool():
    import importlib
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    return importlib.import_module("hook_purchase")


def test_detect_trampoline_tail_calls_spendmoney():
    hp = _load_hook_tool()
    code = hp.build_detect_tramp()
    words = [struct.unpack_from("<I", code, i)[0] for i in range(0, len(code), 4)]
    # last non-nop control word is `jr t9`; the lui/ori before it target SpendMoney
    assert 0x03200008 in words                     # jr t9
    lui = next(w for w in words if (w >> 26) == 0x0F and (w >> 16 & 0x1F) == 25)
    ori = next(w for w in words if (w >> 26) == 0x0D and (w >> 16 & 0x1F) == 25)
    target = ((lui & 0xFFFF) << 16) | (ori & 0xFFFF)
    assert target == hp.SPEND_MONEY


def test_deny_trampoline_tail_calls_uiset_and_guards():
    hp = _load_hook_tool()
    code = hp.build_deny_tramp()
    words = [struct.unpack_from("<I", code, i)[0] for i in range(0, len(code), 4)]
    # tail-calls UISet
    ori_targets = {((lu & 0xFFFF) << 16) | (wo & 0xFFFF)
                   for lu in words if (lu >> 26) == 0x0F
                   for wo in words if (wo >> 26) == 0x0D}
    assert hp.UI_SET in ori_targets
    assert hp.CARCFG_INDEX_FN in ori_targets       # resolves index via game fn
    # clears pending flag: sb zero, 0x79BD(reg)  (op 0x28, rt=0, imm=0x79BD)
    assert any((w >> 26) == 0x28 and (w >> 16 & 0x1F) == 0 and (w & 0xFFFF) == 0x79BD
               for w in words)


def test_hook_expected_originals_match():
    hp = _load_hook_tool()
    # guards used before patching must match the disassembled JAL words
    assert hp.DETECT_ORIG == (0x0C000000 | (hp.SPEND_MONEY >> 2))
    assert hp.DENY_ORIG == (0x0C000000 | (hp.UI_SET >> 2))
