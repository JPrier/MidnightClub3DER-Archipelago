"""SetCarCfg instrumentation — log every call's args to a mailbox ring.

Instruments the FIRST SetCarCfg call site (0x004AE100) by chaining through
the existing payload trampoline at 0x00720040. This supplements the existing
instrumentation on the second site (0x004AE080) which never fires.

Ring layout (EE):
  0x00720700  u32 call_count
  0x00720704  u32 ring_head (0..7)
  0x00720710  8 x 0x18-byte records: [a0, a1, a2, a3, ra, pad]

Usage:
  python tools/instrument_setcarcfg_first_site.py install    # write trampoline + patch JAL
  python tools/instrument_setcarcfg_first_site.py status     # dump ring + decode vehNames
  python tools/instrument_setcarcfg_first_site.py restore    # unpatch
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from mips_assembler import MIPSAssembler, R  # noqa: E402

CALL_SITE = 0x004AE100            # first site 0x004AE100 -> JAL 0x00720040 (build-13 payload)
CURRENT_INSTR = 0x0C1C8010        # CURRENT: JAL 0x00720040 (payload trampoline)
ORIG_INSTR = 0x0C1748E0           # GAME ORIGINAL: JAL 0x005D2380 (SetCarCfg function)
ORIG_TARGET = 0x005D2380
PAYLOAD_TRAMP = 0x00720040         # build-13 payload trampoline we chain through
TRAMP_ADDR = 0x00720880           # free payload area past the existing second-site trampoline
RING_BASE = 0x00720700
RING_RECORDS = 0x00720710
REC_SIZE = 0x18
REC_COUNT = 8


def build_trampoline() -> bytes:
    asm = MIPSAssembler(base=TRAMP_ADDR)

    # prologue: save ra on stack (a0-a3 must reach the real callee untouched)
    asm.addiu(R.SP, R.SP, -16)
    asm.sw(R.RA, R.SP, 0)

    asm.lui(R.AT, 0x0072)                 # at = 0x00720000

    # count++
    asm.lw(R.T8, R.AT, 0x0700)
    asm.addiu(R.T8, R.T8, 1)
    asm.sw(R.T8, R.AT, 0x0700)

    # head = (head + 1) & 7 ; record base = 0x710 + head*0x18
    asm.lw(R.T8, R.AT, 0x0704)
    asm.addiu(R.T8, R.T8, 1)
    asm.andi(R.T8, R.T8, 7)
    asm.sw(R.T8, R.AT, 0x0704)
    # t9 = t8 * 0x18 = (t8<<4) + (t8<<3)
    asm.sll(R.T9, R.T8, 4)
    asm.sll(R.T8, R.T8, 3)
    asm.addu(R.T9, R.T9, R.T8)
    asm.addu(R.T9, R.T9, R.AT)            # t9 = 0x00720000 + head*0x18

    asm.sw(R.A0, R.T9, 0x0710)
    asm.sw(R.A1, R.T9, 0x0714)
    asm.sw(R.A2, R.T9, 0x0718)
    asm.sw(R.A3, R.T9, 0x071C)
    asm.sw(R.RA, R.T9, 0x0720)            # caller return address

    # call existing payload trampoline (build-13 at 0x00720040) — NOT the original SetCarCfg
    asm.lui(R.T9, (PAYLOAD_TRAMP >> 16) & 0xFFFF)
    asm.ori(R.T9, R.T9, PAYLOAD_TRAMP & 0xFFFF)
    asm.jalr(R.T9)
    asm.nop()

    # epilogue
    asm.lw(R.RA, R.SP, 0)
    asm.addiu(R.SP, R.SP, 16)
    asm.jr(R.RA)
    asm.nop()

    return asm.link()


def encode_jal(target: int) -> int:
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


def connect():
    from mc3api import MC3Game
    return MC3Game.connect(timeout=20)


def cmd_install():
    game = connect()
    current = game.read_u32(CALL_SITE)
    if current == encode_jal(TRAMP_ADDR):
        print("already installed")
        game.close()
        return
    if current != CURRENT_INSTR:
        print(f"[ABORT] unexpected instr at 0x{CALL_SITE:08X}: 0x{current:08X} "
              f"(expected 0x{CURRENT_INSTR:08X} = JAL to payload trampoline at 0x{PAYLOAD_TRAMP:08X})")
        game.close()
        return
    code = build_trampoline()
    game.write(TRAMP_ADDR, code)
    # zero the ring
    game.write(RING_BASE, b"\x00" * (0x10 + REC_COUNT * REC_SIZE))
    game.write_u32(CALL_SITE, encode_jal(TRAMP_ADDR))
    print(f"installed: {len(code)} bytes at 0x{TRAMP_ADDR:08X}, "
          f"JAL patched at 0x{CALL_SITE:08X} -> 0x{TRAMP_ADDR:08X}")
    game.close()


def cmd_restore():
    game = connect()
    current = game.read_u32(CALL_SITE)
    if current != encode_jal(TRAMP_ADDR):
        print(f"[ABORT] unexpected current instr 0x{current:08X}, expected JAL to 0x{TRAMP_ADDR:08X}")
        game.close()
        return
    game.write_u32(CALL_SITE, encode_jal(PAYLOAD_TRAMP))
    print(f"restored: JAL -> 0x{PAYLOAD_TRAMP:08X} (build-13 payload)")
    game.close()


def cmd_status():
    game = connect()
    count = game.read_u32(RING_BASE)
    head = game.read_u32(RING_BASE + 4)
    print(f"call_count={count} ring_head={head}")
    for i in range(REC_COUNT):
        rec = game.read(RING_RECORDS + i * REC_SIZE, REC_SIZE)
        a0, a1, a2, a3, ra = struct.unpack("<5I", rec[:20])
        if not any((a0, a1, a2, a3, ra)):
            continue
        line = f"  [{i}] a0={a0:#010x} a1={a1:#010x} a2={a2:#010x} a3={a3:#010x} ra={ra:#010x}"
        # try to decode strings behind pointer-looking args
        for name, v in (("a0", a0), ("a1", a1), ("a2", a2), ("a3", a3)):
            if 0x00100000 < v < 0x02000000:
                try:
                    s = game.bridge.read_cstring(v, 32)
                    if s and all(32 <= ord(c) < 127 for c in s) and len(s) > 3:
                        line += f"  *{name}={s!r}"
                except Exception:
                    pass
        print(line)
    game.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"install": cmd_install, "restore": cmd_restore, "status": cmd_status}[cmd]()