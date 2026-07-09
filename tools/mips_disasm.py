"""Minimal MIPS R5900 (EE) disassembler over the cached ELF code image.

Covers the common integer subset needed for reading MC3 game code:
loads/stores, ALU ops, branches, jumps, lui, and a few EE extras.
Unknown encodings print as raw .word.

Usage:
  python tools/mips_disasm.py <addr> [len_bytes]        # default 0x100
  python tools/mips_disasm.py func <addr>               # disassemble enclosing function
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from static_xref import ELF_BASE, function_start, load_image  # noqa: E402

REG = [
    "zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
    "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
    "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
    "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra",
]

I_OPS = {
    0x04: "beq", 0x05: "bne", 0x06: "blez", 0x07: "bgtz",
    0x08: "addi", 0x09: "addiu", 0x0A: "slti", 0x0B: "sltiu",
    0x0C: "andi", 0x0D: "ori", 0x0E: "xori",
    0x14: "beql", 0x15: "bnel",
    0x18: "daddi", 0x19: "daddiu",
    0x20: "lb", 0x21: "lh", 0x22: "lwl", 0x23: "lw",
    0x24: "lbu", 0x25: "lhu", 0x26: "lwr", 0x27: "lwu",
    0x28: "sb", 0x29: "sh", 0x2A: "swl", 0x2B: "sw",
    0x37: "ld", 0x3F: "sd", 0x1E: "lq", 0x1F: "sq",
    0x31: "lwc1", 0x39: "swc1",
}

R_FUNCS = {
    0x00: "sll", 0x02: "srl", 0x03: "sra",
    0x04: "sllv", 0x06: "srlv", 0x07: "srav",
    0x08: "jr", 0x09: "jalr",
    0x0A: "movz", 0x0B: "movn",
    0x0C: "syscall", 0x0D: "break",
    0x10: "mfhi", 0x11: "mthi", 0x12: "mflo", 0x13: "mtlo",
    0x18: "mult", 0x19: "multu", 0x1A: "div", 0x1B: "divu",
    0x20: "add", 0x21: "addu", 0x22: "sub", 0x23: "subu",
    0x24: "and", 0x25: "or", 0x26: "xor", 0x27: "nor",
    0x2A: "slt", 0x2B: "sltu",
    0x2C: "dadd", 0x2D: "daddu", 0x2E: "dsub", 0x2F: "dsubu",
    0x38: "dsll", 0x3A: "dsrl", 0x3B: "dsra",
    0x3C: "dsll32", 0x3E: "dsrl32", 0x3F: "dsra32",
}

REGIMM = {0x00: "bltz", 0x01: "bgez", 0x10: "bltzal", 0x11: "bgezal"}


def s16(v: int) -> int:
    return v - 0x10000 if v >= 0x8000 else v


def decode(pc: int, w: int) -> str:
    if w == 0:
        return "nop"
    op = w >> 26
    rs, rt = (w >> 21) & 0x1F, (w >> 16) & 0x1F
    rd, sa = (w >> 11) & 0x1F, (w >> 6) & 0x1F
    imm = w & 0xFFFF
    if op == 0:
        fn = w & 0x3F
        name = R_FUNCS.get(fn)
        if name is None:
            return f".word 0x{w:08X}"
        if name in ("sll", "srl", "sra", "dsll", "dsrl", "dsra", "dsll32", "dsrl32", "dsra32"):
            return f"{name} {REG[rd]}, {REG[rt]}, {sa}"
        if name == "jr":
            return f"jr {REG[rs]}"
        if name == "jalr":
            return f"jalr {REG[rd]}, {REG[rs]}" if rd != 31 else f"jalr {REG[rs]}"
        if name in ("mfhi", "mflo"):
            return f"{name} {REG[rd]}"
        if name in ("mthi", "mtlo"):
            return f"{name} {REG[rs]}"
        if name in ("mult", "multu", "div", "divu"):
            return f"{name} {REG[rs]}, {REG[rt]}"
        if name in ("syscall", "break"):
            return name
        return f"{name} {REG[rd]}, {REG[rs]}, {REG[rt]}"
    if op == 0x01:
        name = REGIMM.get(rt)
        if name:
            return f"{name} {REG[rs]}, 0x{pc + 4 + (s16(imm) << 2):08X}"
        return f".word 0x{w:08X}"
    if op in (0x02, 0x03):
        target = ((pc + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
        return f"{'j' if op == 2 else 'jal'} 0x{target:08X}"
    if op == 0x0F:
        return f"lui {REG[rt]}, 0x{imm:04X}"
    name = I_OPS.get(op)
    if name is None:
        return f".word 0x{w:08X}"
    if name in ("beq", "bne", "beql", "bnel"):
        return f"{name} {REG[rs]}, {REG[rt]}, 0x{pc + 4 + (s16(imm) << 2):08X}"
    if name in ("blez", "bgtz"):
        return f"{name} {REG[rs]}, 0x{pc + 4 + (s16(imm) << 2):08X}"
    if name in ("addi", "addiu", "slti", "sltiu", "daddi", "daddiu"):
        return f"{name} {REG[rt]}, {REG[rs]}, {s16(imm)}"
    if name in ("andi", "ori", "xori"):
        return f"{name} {REG[rt]}, {REG[rs]}, 0x{imm:04X}"
    # loads/stores
    return f"{name} {REG[rt]}, 0x{s16(imm) & 0xFFFF:04X}({REG[rs]})" if s16(imm) >= 0 else \
        f"{name} {REG[rt]}, {s16(imm)}({REG[rs]})"


def disasm(img: bytes, addr: int, length: int) -> None:
    for pc in range(addr, addr + length, 4):
        off = pc - ELF_BASE
        if off < 0 or off + 4 > len(img):
            break
        w = struct.unpack_from("<I", img, off)[0]
        print(f"  0x{pc:08X}:  {w:08X}  {decode(pc, w)}")


def main() -> None:
    img = load_image()
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if args[0] == "func":
        addr = int(args[1], 16)
        start = function_start(img, addr)
        # walk forward to jr ra (+ delay slot)
        end = start
        for pc in range(start, start + 0x4000, 4):
            w = struct.unpack_from("<I", img, pc - ELF_BASE)[0]
            if w == 0x03E00008:  # jr ra
                end = pc + 8
                break
        print(f"function 0x{start:08X} .. 0x{end:08X} (contains 0x{addr:08X})")
        disasm(img, start, end - start)
    else:
        addr = int(args[0], 16)
        length = int(args[1], 16) if len(args) > 1 else 0x100
        disasm(img, addr, length)


if __name__ == "__main__":
    main()
