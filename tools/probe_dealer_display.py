"""Non-mutating probe: log every showroom item-display call.

Hooks the ENTRY of the showroom item-display function (0x00329480) —
verified via static analysis to be called once per visible dealer row/frame.
The trampoline re-derives the vehicle index the same way the deny gate does
(ctx+0x72C selected -> ctx+0x71C recptr array -> 0x004AF870), reads the
catalog's class/rank fields, and the screen submode (ctx+0x1B4), then replays
the function's own first instruction and jumps back in. It does NOT change
any game behavior — pure observation.

Correlating this ring's (index, f04, f08, submode) against what you actually
see on screen (Locked vs price vs Owned) for a few known cars pins down the
exact availability predicate.

Usage:
  python tools/probe_dealer_display.py install
  python tools/probe_dealer_display.py status      # decodes vehicle names too
  python tools/probe_dealer_display.py restore
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from mips_assembler import MIPSAssembler, R  # noqa: E402

SITE = 0x00329480
ORIG_INSTR = 0x27BDFFA0          # addiu sp, sp, -96 (verified via mips_disasm.py func 0x00329480)
RETURN_ADDR = 0x00329484         # site + 4, function's second instruction
CARCFG_INDEX_FN = 0x004AF870     # (carCfg) -> catalog index
VEHLIST_PTR = 0x006E0170
VEH_STRIDE = 0x1C

TRAMP_ADDR = 0x00720E00
SCRATCH_RA = 0x00720DF0
SCRATCH_CTX = 0x00720DF4
RING_BASE = 0x00720D00
RING_RECS = 0x00720D10
REC_SIZE = 0x10
REC_COUNT = 8


def encode_jal(target: int) -> int:
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


def build_trampoline() -> bytes:
    a = MIPSAssembler(base=TRAMP_ADDR)
    # save true return address + ctx (a0) to static scratch (not stack — the
    # nested call to 0x004AF870 manages its own stack independently)
    a.lui(R.T0, (SCRATCH_RA >> 16) & 0xFFFF)
    a.sw(R.RA, R.T0, SCRATCH_RA & 0xFFFF)
    a.sw(R.A0, R.T0, SCRATCH_CTX & 0xFFFF)

    # recptr = [ctx + 0x71C + selected*4]   (same resolution as the deny gate)
    a.lw(R.T1, R.A0, 0x072C)
    a.sll(R.T1, R.T1, 2)
    a.addu(R.T2, R.A0, R.T1)
    a.lw(R.A0, R.T2, 0x071C)              # a0 = recptr, arg for index fn
    a.lui(R.T9, (CARCFG_INDEX_FN >> 16) & 0xFFFF)
    a.ori(R.T9, R.T9, CARCFG_INDEX_FN & 0xFFFF)
    a.jalr(R.T9)                          # v0 = catalog index
    a.nop()

    # catalog[index]: f04, f08
    a.addiu(R.T3, R.ZERO, VEH_STRIDE)
    a.mult(R.V0, R.T3)
    a.mflo(R.T4)                          # t4 = index * 0x1C  (v0 preserved)
    a.lui(R.T5, (VEHLIST_PTR >> 16) & 0xFFFF)
    a.lw(R.T5, R.T5, VEHLIST_PTR & 0xFFFF)
    a.addu(R.T5, R.T5, R.T4)              # t5 = &catalog[index]
    a.lw(R.T6, R.T5, 0x04)                # f04
    a.lw(R.T7, R.T5, 0x08)                # f08

    # restore ctx, read submode
    a.lui(R.T0, (SCRATCH_CTX >> 16) & 0xFFFF)
    a.lw(R.S0, R.T0, SCRATCH_CTX & 0xFFFF)
    a.lw(R.S1, R.S0, 0x01B4)              # submode

    # ring append: [index, f04, f08, submode]
    a.lui(R.T0, 0x0072)
    a.lw(R.S2, R.T0, RING_BASE & 0xFFFF)
    a.addiu(R.S2, R.S2, 1)
    a.sw(R.S2, R.T0, RING_BASE & 0xFFFF)
    a.lw(R.S3, R.T0, (RING_BASE + 4) & 0xFFFF)
    a.addiu(R.S3, R.S3, 1)
    a.andi(R.S3, R.S3, REC_COUNT - 1)
    a.sw(R.S3, R.T0, (RING_BASE + 4) & 0xFFFF)
    a.sll(R.S4, R.S3, 4)
    a.addu(R.S4, R.S4, R.T0)
    a.sw(R.V0, R.S4, RING_RECS & 0xFFFF)
    a.sw(R.T6, R.S4, (RING_RECS + 4) & 0xFFFF)
    a.sw(R.T7, R.S4, (RING_RECS + 8) & 0xFFFF)
    a.sw(R.S1, R.S4, (RING_RECS + 12) & 0xFFFF)

    # restore ra, a0=ctx; replay original first instruction; jump back in
    a.lui(R.T0, (SCRATCH_RA >> 16) & 0xFFFF)
    a.lw(R.RA, R.T0, SCRATCH_RA & 0xFFFF)
    a.lw(R.A0, R.T0, SCRATCH_CTX & 0xFFFF)
    a.addiu(R.SP, R.SP, -96)              # replay 0x00329480's own first instr
    a.lui(R.T9, (RETURN_ADDR >> 16) & 0xFFFF)
    a.ori(R.T9, R.T9, RETURN_ADDR & 0xFFFF)
    a.jr(R.T9)
    a.nop()
    return a.link()


def connect():
    from mc3api import MC3Game
    return MC3Game.connect(timeout=20)


def cmd_install():
    game = connect()
    cur = game.read_u32(SITE)
    if cur == encode_jal(TRAMP_ADDR):
        print("already installed")
        return game.close()
    if cur != ORIG_INSTR:
        print(f"[ABORT] site 0x{SITE:08X} = 0x{cur:08X}, expected 0x{ORIG_INSTR:08X}")
        return game.close()
    code = build_trampoline()
    game.write(TRAMP_ADDR, code)
    game.write(RING_BASE, b"\x00" * (0x10 + REC_COUNT * REC_SIZE))
    game.write_u32(SITE, encode_jal(TRAMP_ADDR))
    back = game.read_u32(SITE)
    print(f"installed: {len(code)}B @0x{TRAMP_ADDR:08X}; "
          f"{'OK' if back == encode_jal(TRAMP_ADDR) else 'VERIFY-FAILED'}")
    print("Now browse the dealer/showroom in-game (scroll over a few cars, "
          "including at least one you know is Locked). Then run `status`.")
    game.close()


def cmd_restore():
    game = connect()
    cur = game.read_u32(SITE)
    if cur != encode_jal(TRAMP_ADDR):
        print(f"[skip] site not ours: 0x{cur:08X}")
        return game.close()
    game.write_u32(SITE, ORIG_INSTR)
    print(f"restored 0x{SITE:08X} -> addiu sp,sp,-96")
    game.close()


def cmd_status():
    game = connect()
    count = game.read_u32(RING_BASE)
    head = game.read_u32(RING_BASE + 4)
    print(f"call_count={count} ring_head={head}")
    vehicles = {v.index: v.name for v in game.vehicles()}
    for i in range(REC_COUNT):
        rec = game.read(RING_RECS + i * REC_SIZE, REC_SIZE)
        index, f04, f08, submode = struct.unpack("<4I", rec)
        if index == 0 and f04 == 0 and f08 == 0 and submode == 0:
            continue
        name = vehicles.get(index, "?")
        print(f"  [{i}] idx={index:3d} {name:<22s} f04={f04} f08={f08} submode={submode}")
    game.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"install": cmd_install, "restore": cmd_restore, "status": cmd_status}[cmd]()
