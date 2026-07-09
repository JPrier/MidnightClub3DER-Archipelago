"""Static xref analysis over the MC3 ELF code image.

Finds, without running gameplay:
  * JAL call sites to a given function (callers)
  * code that materializes a given address via lui+addiu/ori (data xrefs)
  * strings in the data segment and the code that references them
  * enclosing-function starts (MIPS prologue scan)

The code image is dumped once from live PCSX2 EE RAM (the ELF as loaded),
cached under artifacts/static/ (gitignored — game code is copyrighted).

Usage:
  python tools/static_xref.py dump                    # cache code image from live PCSX2
  python tools/static_xref.py callers 0x005D2380      # who JALs this target
  python tools/static_xref.py dataref 0x00717F88      # who references this address
  python tools/static_xref.py string ShowRoomPrice    # find string + its code refs
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / "artifacts" / "static" / "elf_image.bin"
ELF_BASE = 0x00100000
ELF_END = 0x00800000          # code + data as loaded (covers .text and .data)
TEXT_END = 0x00715BC0         # docs: ELF code+data ends ~0x715BBC


def dump_image() -> bytes:
    sys.path.insert(0, str(REPO))
    from mc3api import MC3Game
    game = MC3Game.connect(timeout=20)
    data = game.read(ELF_BASE, ELF_END - ELF_BASE)
    game.close()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(data)
    print(f"cached {len(data):#x} bytes -> {CACHE}")
    return data


def load_image() -> bytes:
    if CACHE.exists():
        return CACHE.read_bytes()
    return dump_image()


def words(img: bytes):
    return struct.unpack(f"<{len(img)//4}I", img[: len(img) // 4 * 4])


def find_callers(img: bytes, target: int) -> list[int]:
    """All JAL <target> sites in the code segment."""
    jal = 0x0C000000 | ((target >> 2) & 0x03FFFFFF)
    out = []
    ws = words(img)
    limit = (TEXT_END - ELF_BASE) // 4
    for i, w in enumerate(ws[:limit]):
        if w == jal:
            out.append(ELF_BASE + i * 4)
    return out


def find_datarefs(img: bytes, addr: int, window: int = 16) -> list[int]:
    """lui+addiu/ori pairs that materialize addr (within `window` instrs)."""
    lo = addr & 0xFFFF
    hi_addiu = (addr >> 16) + (1 if lo & 0x8000 else 0)  # addiu sign-extends
    hi_ori = addr >> 16
    ws = words(img)
    limit = (TEXT_END - ELF_BASE) // 4
    hits = []
    lui_sites: list[tuple[int, int, int]] = []  # (index, reg, hi)
    for i, w in enumerate(ws[:limit]):
        op = w >> 26
        if op == 0x0F:  # lui rt, imm
            lui_sites.append((i, (w >> 16) & 31, w & 0xFFFF))
        elif op in (0x09, 0x0D):  # addiu / ori
            rs = (w >> 21) & 31
            imm = w & 0xFFFF
            want_hi = hi_addiu if op == 0x09 else hi_ori
            if imm == lo:
                for j, reg, hi in reversed(lui_sites[-64:]):
                    if i - j > window:
                        break
                    if reg == rs and hi == (want_hi & 0xFFFF):
                        hits.append(ELF_BASE + i * 4)
                        break
        # also lw/sw rt, lo(rs) after lui
        elif op in (0x23, 0x2B, 0x20, 0x24, 0x21, 0x25):  # lw/sw/lb/lbu/lh/lhu
            rs = (w >> 21) & 31
            imm = w & 0xFFFF
            if imm == lo:
                for j, reg, hi in reversed(lui_sites[-64:]):
                    if i - j > window:
                        break
                    if reg == rs and hi == (hi_addiu & 0xFFFF):
                        hits.append(ELF_BASE + i * 4)
                        break
    return hits


def find_strings(img: bytes, needle: bytes) -> list[int]:
    out, i = [], 0
    while True:
        i = img.find(needle, i)
        if i < 0:
            break
        out.append(ELF_BASE + i)
        i += 1
    return out


def function_start(img: bytes, addr: int) -> int:
    """Walk back to the nearest `addiu sp, sp, -N` prologue."""
    ws = words(img)
    i = (addr - ELF_BASE) // 4
    for k in range(i, max(0, i - 4096), -1):
        w = ws[k]
        if (w >> 16) == 0x27BD and (w & 0x8000):  # addiu sp,sp,-N
            return ELF_BASE + k * 4
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "dump":
        dump_image()
        return 0

    img = load_image()
    if cmd == "callers":
        target = int(sys.argv[2], 16)
        callers = find_callers(img, target)
        print(f"JAL 0x{target:08X} call sites: {len(callers)}")
        for c in callers:
            f = function_start(img, c)
            print(f"  0x{c:08X}  (in function 0x{f:08X})")
    elif cmd == "dataref":
        addr = int(sys.argv[2], 16)
        refs = find_datarefs(img, addr)
        print(f"code refs to 0x{addr:08X}: {len(refs)}")
        for r in refs:
            f = function_start(img, r)
            print(f"  0x{r:08X}  (in function 0x{f:08X})")
    elif cmd == "string":
        needle = sys.argv[2].encode()
        locs = find_strings(img, needle)
        print(f"string {needle!r}: {len(locs)} occurrences")
        for s in locs[:20]:
            refs = find_datarefs(img, s)
            print(f"  0x{s:08X}  code refs: {[hex(r) for r in refs[:8]]}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
