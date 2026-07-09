"""Minimal MIPS R5900 assembler for PS2 EE payload code.

Encodes a small subset of MIPS III instructions needed for the MC3AP payload.
Emits raw binary, PNACH word-patches, and hex dump.

MIPS encoding reference:
  R-type: [opcode(6) | rs(5) | rt(5) | rd(5) | shamt(5) | funct(6)]
  I-type: [opcode(6) | rs(5) | rt(5) | immediate(16)]
  J-type: [opcode(6) | target(26)]
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Register map
# ---------------------------------------------------------------------------

class Reg(Enum):
    ZERO = 0
    AT   = 1    # assembler temporary
    V0   = 2    # return value
    V1   = 3
    A0   = 4    # argument
    A1   = 5
    A2   = 6
    A3   = 7
    T0   = 8    # temp
    T1   = 9
    T2   = 10
    T3   = 11
    T4   = 12
    T5   = 13
    T6   = 14
    T7   = 15
    S0   = 16   # saved
    S1   = 17
    S2   = 18
    S3   = 19
    S4   = 20
    S5   = 21
    S6   = 22
    S7   = 23
    T8   = 24   # temp
    T9   = 25
    K0   = 26   # kernel
    K1   = 27
    GP   = 28   # global pointer
    SP   = 29   # stack pointer
    FP   = 30   # frame pointer
    RA   = 31   # return address


# Aliases
R = Reg


# ---------------------------------------------------------------------------
# Opcodes
# ---------------------------------------------------------------------------

# R-type funct codes
FUNCT = {
    "ADD":   0x20, "ADDU":  0x21, "AND":   0x24,
    "JR":    0x08, "JALR":  0x09,
    "NOR":   0x27, "OR":    0x25,
    "SLT":   0x2A, "SLTU":  0x2B,
    "SLL":   0x00, "SRL":   0x02, "SRA":   0x03,
    "SUB":   0x22, "SUBU":  0x23,
    "SYSCALL": 0x0C,
    "MULT":  0x18, "MFLO":  0x12, "MFHI": 0x10,
    "XOR":   0x26,
}

# I-type opcodes (top 6 bits)
I_OP = {
    "ADDI":  0x08, "ADDIU": 0x09,
    "ANDI":  0x0C,
    "BEQ":   0x04, "BNE":   0x05,
    "LUI":   0x0F,
    "LW":    0x23, "SW":    0x2B,
    "LB":    0x20, "SB":    0x28,
    "ORI":   0x0D,
    "SLTI":  0x0A, "SLTIU": 0x0B,
    "XORI":  0x0E,
}

# J-type opcodes
J_OP = {
    "J":     0x02, "JAL":   0x03,
}


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

@dataclass
class Instruction:
    """One encoded MIPS instruction at a known address."""
    addr: int
    word: int
    mnemonic: str = ""
    comment: str = ""


@dataclass
class Label:
    name: str
    addr: int


class MIPSAssembler:
    """Minimal two-pass MIPS assembler for MC3AP payload.

    Usage:
        asm = MIPSAssembler(base=0x00710000)
        asm.lui(R.T0, 0x0071)
        asm.ori(R.T0, R.T0, 0x0004)
        asm.emit(label="my_label")
        asm.jr(R.RA)
        bin_data = asm.link()
        pnach = asm.to_pnach()
    """

    def __init__(self, base: int = 0x00710000):
        self._base = base
        self._instructions: List[Instruction] = []
        self._labels: dict[str, int] = {}       # name -> addr
        self._pending: list[tuple[int, str, str]] = []  # (instr_idx, label_name, instr_type)

    # ── instruction encoders ───────────────────────────────────────────────

    def _emit(self, word: int, mnemonic: str = "", comment: str = ""):
        addr = self._base + len(self._instructions) * 4
        self._instructions.append(Instruction(addr, word, mnemonic, comment))

    def lbl(self, name: str):
        """Define a label at the current position."""
        addr = self._base + len(self._instructions) * 4
        self._labels[name] = addr

    def nop(self):
        self._emit(0x00000000, "nop")

    # ── R-type ─────────────────────────────────────────────────────────────

    def _r(self, funct: str, rd: Reg, rs: Reg, rt: Reg, shamt: int = 0):
        code = FUNCT[funct]
        return (0 << 26) | (rs.value << 21) | (rt.value << 16) | (rd.value << 11) | (shamt << 6) | code

    def add(self, rd: Reg, rs: Reg, rt: Reg):
        self._emit(self._r("ADD", rd, rs, rt), f"add {rd.name}, {rs.name}, {rt.name}")

    def addu(self, rd: Reg, rs: Reg, rt: Reg):
        self._emit(self._r("ADDU", rd, rs, rt), f"addu {rd.name}, {rs.name}, {rt.name}")

    def subu(self, rd: Reg, rs: Reg, rt: Reg):
        self._emit(self._r("SUBU", rd, rs, rt), f"subu {rd.name}, {rs.name}, {rt.name}")

    def and_(self, rd: Reg, rs: Reg, rt: Reg):
        self._emit(self._r("AND", rd, rs, rt), f"and {rd.name}, {rs.name}, {rt.name}")

    def or_(self, rd: Reg, rs: Reg, rt: Reg):
        self._emit(self._r("OR", rd, rs, rt), f"or {rd.name}, {rs.name}, {rt.name}")

    def slt(self, rd: Reg, rs: Reg, rt: Reg):
        self._emit(self._r("SLT", rd, rs, rt), f"slt {rd.name}, {rs.name}, {rt.name}")

    def sll(self, rd: Reg, rt: Reg, shamt: int):
        self._emit(self._r("SLL", rd, Reg.ZERO, rt, shamt), f"sll {rd.name}, {rt.name}, {shamt}")

    def jr(self, rs: Reg):
        self._emit(self._r("JR", Reg.ZERO, rs, Reg.ZERO), f"jr {rs.name}")

    def jalr(self, rs: Reg, rd: Reg = Reg.RA):
        self._emit(self._r("JALR", rd, rs, Reg.ZERO), f"jalr {rd.name}, {rs.name}")

    def mflo(self, rd: Reg):
        self._emit(self._r("MFLO", rd, Reg.ZERO, Reg.ZERO), f"mflo {rd.name}")

    def mfhi(self, rd: Reg):
        self._emit(self._r("MFHI", rd, Reg.ZERO, Reg.ZERO), f"mfhi {rd.name}")

    def mult(self, rs: Reg, rt: Reg):
        self._emit(self._r("MULT", Reg.ZERO, rs, rt), f"mult {rs.name}, {rt.name}")

    # ── I-type ─────────────────────────────────────────────────────────────

    def _i(self, op: str, rt: Reg, rs: Reg, imm: int):
        code = I_OP[op]
        return (code << 26) | (rs.value << 21) | (rt.value << 16) | (imm & 0xFFFF)

    def _imm16(self, value: int) -> int:
        """Clamp to signed 16-bit for immediate fields."""
        if value < -32768 or value > 65535:
            raise ValueError(f"Immediate {value} out of 16-bit range")
        return value & 0xFFFF

    def addiu(self, rt: Reg, rs: Reg, imm: int):
        imm = self._imm16(imm)
        self._emit(self._i("ADDIU", rt, rs, imm), f"addiu {rt.name}, {rs.name}, {imm:#x}")

    def lui(self, rt: Reg, imm: int):
        imm = self._imm16(imm)
        self._emit(self._i("LUI", rt, Reg.ZERO, imm), f"lui {rt.name}, {imm:#x}")

    def ori(self, rt: Reg, rs: Reg, imm: int):
        imm = self._imm16(imm)
        self._emit(self._i("ORI", rt, rs, imm), f"ori {rt.name}, {rs.name}, {imm:#x}")

    def andi(self, rt: Reg, rs: Reg, imm: int):
        imm = self._imm16(imm)
        self._emit(self._i("ANDI", rt, rs, imm), f"andi {rt.name}, {rs.name}, {imm:#x}")

    def lw(self, rt: Reg, base: Reg, offset: int = 0):
        offset = self._imm16(offset)
        self._emit(self._i("LW", rt, base, offset), f"lw {rt.name}, {offset}({base.name})")

    def sw(self, rt: Reg, base: Reg, offset: int = 0):
        offset = self._imm16(offset)
        self._emit(self._i("SW", rt, base, offset), f"sw {rt.name}, {offset}({base.name})")

    def beq(self, rs: Reg, rt: Reg, label: str):
        idx = len(self._instructions)
        self._pending.append((idx, label, "BEQ"))
        self._emit(0, f"beq {rs.name}, {rt.name}, {label}")  # placeholder
        # Store rs, rt for later
        self._instructions[-1].comment = f"rs={rs.name} rt={rt.name} label={label}"

    def bne(self, rs: Reg, rt: Reg, label: str):
        idx = len(self._instructions)
        self._pending.append((idx, label, "BNE"))
        self._emit(0, f"bne {rs.name}, {rt.name}, {label}")
        self._instructions[-1].comment = f"rs={rs.name} rt={rt.name} label={label}"

    def _resolve_branch(self, idx: int, label: str, op: str):
        """Resolve a branch target with delay-slot aware offset."""
        instr = self._instructions[idx]
        target = self._labels.get(label)
        if target is None:
            raise ValueError(f"Undefined label: {label}")

        # Branch offset is relative to the DELAY SLOT (PC + 8 in MIPS terms)
        # Actually: branch offset = (target - pc - 4) / 4
        # Where pc is the branch instruction address
        # The MIPS offset counts instructions from the delay slot
        branch_pc = instr.addr
        offset = (target - branch_pc - 4) >> 2  # in instructions
        offset = offset & 0xFFFF

        # Parse the stored rs/rt from comment
        parts = instr.comment.split() if instr.comment else []
        rs_name = ""
        rt_name = ""
        for part in parts:
            if part.startswith("rs="):
                rs_name = part.split("=")[1]
            elif part.startswith("rt="):
                rt_name = part.split("=")[1]

        rs = Reg[rs_name] if rs_name else Reg.ZERO
        rt = Reg[rt_name] if rt_name else Reg.ZERO

        word = self._i(op, rt, rs, offset) if op in ("BEQ", "BNE") else 0
        # Actually BNE uses rt first: beq/bne rs, rt, offset
        # So: (opcode << 26) | (rs << 21) | (rt << 16) | offset
        # That's what _i does: rs in rs position, rt in rt position
        word = self._i(op, rt, rs, offset)
        self._instructions[idx] = Instruction(branch_pc, word, instr.mnemonic, instr.comment)

    def j(self, label: str):
        idx = len(self._instructions)
        self._pending.append((idx, label, "J"))
        self._emit(0, f"j {label}")

    def jal(self, label: str):
        idx = len(self._instructions)
        self._pending.append((idx, label, "JAL"))
        self._emit(0, f"jal {label}")

    def _resolve_jump(self, idx: int, label: str, op: str):
        instr = self._instructions[idx]
        target = self._labels.get(label)
        if target is None:
            raise ValueError(f"Undefined label: {label}")

        # J-type: target = (addr >> 2) & 0x03FFFFFF
        jop = J_OP[op]
        word = (jop << 26) | ((target >> 2) & 0x03FFFFFF)
        self._instructions[idx] = Instruction(instr.addr, word, instr.mnemonic, instr.comment)

    # ── higher-level helpers ───────────────────────────────────────────────

    def load_addr(self, reg: Reg, addr: int):
        """Load a 32-bit address into a register (lui + ori)."""
        upper = (addr >> 16) & 0xFFFF
        lower = addr & 0xFFFF
        self.lui(reg, upper)
        if lower:
            self.ori(reg, reg, lower)

    def load_imm(self, reg: Reg, value: int):
        """Load a 32-bit immediate into a register."""
        upper = (value >> 16) & 0xFFFF
        lower = value & 0xFFFF
        self.lui(reg, upper)
        if lower:
            self.ori(reg, reg, lower)

    # ── linking ────────────────────────────────────────────────────────────

    def link(self) -> bytes:
        """Resolve all labels and return the final bytecode."""
        for idx, label, op in self._pending:
            if op in ("BEQ", "BNE"):
                self._resolve_branch(idx, label, op)
            elif op in ("J", "JAL"):
                self._resolve_jump(idx, label, op)

        result = bytearray()
        for instr in self._instructions:
            result.extend(struct.pack("<I", instr.word))
        return bytes(result)

    # ── output formats ─────────────────────────────────────────────────────

    def to_pnach(self, comment_prefix: str = "//") -> str:
        """Generate PCSX2 PNACH patch directives."""
        binary = self.link()
        lines = []
        lines.append(f"{comment_prefix} MC3AP payload — auto-generated by mips_assembler.py")
        lines.append(f"{comment_prefix} {len(self._instructions)} instructions, base 0x{self._base:08X}")
        lines.append("")

        for i in range(0, len(binary), 4):
            word = struct.unpack("<I", binary[i:i+4])[0]
            addr = self._base + i
            comment = ""
            if i // 4 < len(self._instructions):
                instr = self._instructions[i // 4]
                if instr.mnemonic:
                    comment = f" {comment_prefix} {instr.mnemonic}"
            lines.append(f"patch=1,EE,{addr:08X},word,{word:08X}{comment}")

        return "\n".join(lines)

    def hexdump(self) -> str:
        """Hex dump of linked binary."""
        binary = self.link()
        lines = []
        for i in range(0, len(binary), 16):
            chunk = binary[i:i+16]
            addr = self._base + i
            hex_part = " ".join(f"{b:02X}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"  {addr:08X}: {hex_part:<48s} {ascii_part}")
        return "\n".join(lines)

    def disasm(self) -> str:
        """Disassembly listing."""
        binary = self.link()
        lines = []
        for i, instr in enumerate(self._instructions):
            word = struct.unpack("<I", binary[i*4:(i+1)*4])[0]
            lines.append(f"  {instr.addr:08X}: {word:08X}  {instr.mnemonic}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asm = MIPSAssembler(base=0x00710000)

    # Simple test: load 0xDEADBEEF into t1, store to 0x00710004
    asm.load_imm(R.T1, 0xDEADBEEF)
    asm.lui(R.T0, 0x0071)
    asm.ori(R.T0, R.T0, 0x0004)
    asm.sw(R.T1, R.T0, 0)
    asm.jr(R.RA)
    asm.nop()

    print("=== Disassembly ===")
    print(asm.disasm())
    print()
    print("=== Hex Dump ===")
    print(asm.hexdump())
    print()
    print("=== PNACH ===")
    print(asm.to_pnach())