"""MIPS static analyzer — function boundaries, JAL sites, instruction classification.

Reads a MIPS ELF binary and produces:
  - function boundaries (prologue/epilogue detection)
  - JAL call sites with targets
  - instruction classification for any given address
  - candidate hook points for unsafe instruction sites

No Ghidra required. Used as Stage 2 input for automated hook discovery.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ── MIPS opcodes ─────────────────────────────────────────────────────────────

JAL_OP  = 0x03
J_OP    = 0x02
JR_OP   = 0x00  # funct 0x08
JALR_OP = 0x00  # funct 0x09
ADDIU   = 0x09
SW      = 0x2B
LW      = 0x23
LUI     = 0x0F
ORI     = 0x0D
BEQ     = 0x04
BNE     = 0x05


def decode_op(instr: int) -> int:
    return (instr >> 26) & 0x3F


def decode_funct(instr: int) -> int:
    return instr & 0x3F


def decode_rs(instr: int) -> int:
    return (instr >> 21) & 0x1F


def decode_rt(instr: int) -> int:
    return (instr >> 16) & 0x1F


def decode_imm(instr: int) -> int:
    return instr & 0xFFFF


def decode_jal_target(instr: int) -> int:
    return (instr & 0x03FFFFFF) << 2


def is_return(instr: int) -> bool:
    """Detect JR RA (return from function)."""
    return decode_op(instr) == 0x00 and decode_funct(instr) == 0x08 and decode_rs(instr) == 31


def is_jal(instr: int) -> bool:
    return decode_op(instr) == JAL_OP


def is_jump(instr: int) -> bool:
    return decode_op(instr) == J_OP


def is_branch(instr: int) -> bool:
    return decode_op(instr) in (BEQ, BNE, 0x06, 0x07, 0x01)


# ── Prologue / epilogue patterns ─────────────────────────────────────────────

# Common MIPS prologues:
#   addiu sp, sp, -N  (0x27BDFFxx)
#   sw ra, N(sp)      (0xAFBFxxxx)
#   sw s0, N(sp)      (0xAFB0xxxx)
PROLOGUE_PATTERNS = [
    (0x27BD0000, 0xFFFF0000),   # addiu sp, sp, -N (mask out immediate)
    (0xAFBF0000, 0xFFFF0000),   # sw ra, N(sp)
]


def is_prologue(instr: int) -> bool:
    for pattern, mask in PROLOGUE_PATTERNS:
        if (instr & mask) == pattern:
            return True
    return False


# ── Function scanner ──────────────────────────────────────────────────────────

@dataclass
class Function:
    start: int
    end: int
    size: int
    callers: List[int] = field(default_factory=list)
    callees: List[int] = field(default_factory=list)
    instructions: List[int] = field(default_factory=list)

    @property
    def addr_range(self) -> Tuple[int, int]:
        return (self.start, self.end)


@dataclass
class HookCandidate:
    kind: str            # "caller_jal", "function_entry_inline", "function_entry_jal"
    patch_addr: int
    original_instr: int
    original_target: Optional[int] = None
    confidence: float = 0.0
    reason: str = ""


@dataclass
class ScanResult:
    elf_base: int
    elf_size: int
    functions: List[Function]
    all_jal_sites: Dict[int, int]   # caller_addr -> target_addr
    all_jr_sites: List[int]         # addresses of JR RA instructions


class MIPSScanner:
    """Scans a MIPS ELF for function boundaries, JAL sites, and hook candidates."""

    def __init__(self, elf_data: bytes, elf_base: int = 0x001A0000):
        self._data = elf_data
        self._base = elf_base
        self._size = len(elf_data)

    def read_instr(self, ee_addr: int) -> Optional[int]:
        """Read a MIPS instruction from the ELF by EE address."""
        file_off = ee_addr - self._base
        if 0 <= file_off < self._size - 3:
            return struct.unpack_from("<I", self._data, file_off)[0]
        return None

    def find_functions(self) -> ScanResult:
        """Scan the ELF for function boundaries using heuristics."""
        functions: List[Function] = []
        all_jal_sites: Dict[int, int] = {}
        all_jr_sites: List[int] = []

        # Scan in earnest: find JAL targets as function starts,
        # and JR RA as function ends
        jal_targets: Set[int] = set()

        # First pass: collect all JAL targets and JR sites
        for file_off in range(0, self._size, 4):
            ee_addr = self._base + file_off
            instr = struct.unpack_from("<I", self._data, file_off)[0]

            if is_jal(instr):
                target = decode_jal_target(instr)
                jal_targets.add(target)
                all_jal_sites[ee_addr] = target

            if is_return(instr):
                all_jr_sites.append(ee_addr)

        # Second pass: build functions from JAL targets → nearest JR
        for start in sorted(jal_targets):
            if not (self._base <= start < self._base + self._size):
                continue

            # Find next JR RA after this start
            end = None
            for jr_addr in sorted(all_jr_sites):
                if jr_addr > start:
                    end = jr_addr + 4  # include delay slot
                    break

            if end is None:
                end = start + 0x100  # arbitrary fallback

            size = end - start
            if 4 <= size <= 0x10000:  # sanity bounds
                functions.append(Function(start=start, end=end, size=size))

        # Third pass: cross-reference callers/callees
        func_starts = {f.start for f in functions}
        for f in functions:
            for ee_addr, target in all_jal_sites.items():
                if target == f.start and self._base <= ee_addr < self._base + self._size:
                    f.callers.append(ee_addr)
                if target in func_starts:
                    f.callees.append(target)

        return ScanResult(
            elf_base=self._base,
            elf_size=self._size,
            functions=functions,
            all_jal_sites=all_jal_sites,
            all_jr_sites=all_jr_sites,
        )

    def classify_instruction_site(self, ee_addr: int) -> dict:
        """Determine what kind of instruction is at an address."""
        instr = self.read_instr(ee_addr)
        if instr is None:
            return {"error": "out of range"}

        op = decode_op(instr)
        funct = decode_funct(instr)
        rs = decode_rs(instr)

        if op == JAL_OP:
            return {
                "kind": "jal",
                "target": decode_jal_target(instr),
                "safe_for_trampoline": True,
            }
        elif op == J_OP:
            return {"kind": "j", "target": (instr & 0x03FFFFFF) << 2, "safe_for_trampoline": True}
        elif op == JR_OP and funct == 0x08:
            return {"kind": "jr", "rs": rs, "likely_return": rs == 31, "safe_for_trampoline": False}
        elif op == 0x00 and funct == 0x09:
            return {"kind": "jalr", "rs": rs, "safe_for_trampoline": False}
        elif op == ADDIU and rs == 29 and decode_rt(instr) == 29:
            return {"kind": "prologue", "stack_adj": decode_imm(instr), "safe_for_trampoline": True}
        elif op == SW and rs == 29 and decode_rt(instr) == 31:
            return {"kind": "save_ra", "safe_for_trampoline": True}
        elif is_branch(instr):
            return {"kind": "branch", "safe_for_trampoline": False}
        else:
            return {"kind": "generic_instruction", "op": op, "funct": funct, "safe_for_trampoline": False}

    def find_hook_candidates(self, target_addr: int, result: ScanResult) -> List[HookCandidate]:
        """Find safe hook candidates for an unsafe instruction site."""
        candidates: List[HookCandidate] = []

        # Strategy 1: Find the function containing this address
        containing_func = None
        for f in result.functions:
            if f.start <= target_addr < f.end:
                containing_func = f
                break

        if containing_func:
            # Candidate: inline hook at function entry
            candidates.append(HookCandidate(
                kind="function_entry_inline",
                patch_addr=containing_func.start,
                original_instr=self.read_instr(containing_func.start) or 0,
                confidence=0.68,
                reason=f"function containing target (0x{containing_func.start:08X}-0x{containing_func.end:08X})",
            ))

            # Candidate: each caller JAL
            for caller in containing_func.callers:
                orig = self.read_instr(caller) or 0
                target = decode_jal_target(orig) if is_jal(orig) else 0
                candidates.append(HookCandidate(
                    kind="caller_jal",
                    patch_addr=caller,
                    original_instr=orig,
                    original_target=target,
                    confidence=0.55,
                    reason=f"JAL caller of containing function at 0x{caller:08X}",
                ))

        # Strategy 2: Find nearby JAL instructions
        for offset in range(-0x100, 0x100, 4):
            addr = target_addr + offset
            instr = self.read_instr(addr)
            if instr and is_jal(instr):
                target = decode_jal_target(instr)
                candidates.append(HookCandidate(
                    kind="nearby_jal",
                    patch_addr=addr,
                    original_instr=instr,
                    original_target=target,
                    confidence=0.3,
                    reason=f"JAL at offset {offset:+d} from target",
                ))

        # Deduplicate and sort by confidence
        seen = set()
        unique = []
        for c in sorted(candidates, key=lambda c: c.confidence, reverse=True):
            key = (c.patch_addr, c.kind)
            if key not in seen:
                seen.add(key)
                unique.append(c)

        return unique


# ── CLI ──────────────────────────────────────────────────────────────────────

def load_elf_from_iso(iso_path: str, sector: int = 544) -> bytes:
    """Extract the ELF from a PS2 ISO at a given sector."""
    with open(iso_path, "rb") as f:
        f.seek(sector * 2048)
        return f.read(8 * 1024 * 1024)


def cmd_scan(iso_path: str, target_name: str, target_addr: int, output: str):
    """Scan the ELF and produce hook candidates for a target address."""
    elf = load_elf_from_iso(iso_path)
    scanner = MIPSScanner(elf)
    result = scanner.find_functions()

    print(f"ELF: {len(elf)} bytes, {len(result.functions)} functions found")
    print(f"JAL sites: {len(result.all_jal_sites)}, JR RA sites: {len(result.all_jr_sites)}")

    # Classify the target
    classification = scanner.classify_instruction_site(target_addr)
    print(f"\nTarget 0x{target_addr:08X} classification: {json.dumps(classification, indent=2)}")

    # Find candidates
    candidates = scanner.find_hook_candidates(target_addr, result)
    print(f"\nHook candidates for {target_name}:")
    for i, c in enumerate(candidates):
        print(f"  [{i}] {c.kind} @ 0x{c.patch_addr:08X} (conf={c.confidence:.2f})")
        print(f"      orig=0x{c.original_instr:08X}", end="")
        if c.original_target:
            print(f" target=0x{c.original_target:08X}", end="")
        print()
        print(f"      {c.reason}")

    # Write output
    import os
    os.makedirs(os.path.dirname(output) if os.path.dirname(output) else ".", exist_ok=True)
    report = {
        "target": target_name,
        "observed_addr": f"0x{target_addr:08X}",
        "classification": classification,
        "functions_found": len(result.functions),
        "candidates": [
            {
                "kind": c.kind,
                "patch_addr": f"0x{c.patch_addr:08X}",
                "original_instr": f"0x{c.original_instr:08X}",
                "original_target": f"0x{c.original_target:08X}" if c.original_target else None,
                "confidence": c.confidence,
                "reason": c.reason,
            }
            for c in candidates
        ],
    }
    with open(output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport written to {output}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 5:
        cmd_scan(sys.argv[1], sys.argv[2], int(sys.argv[3], 16), sys.argv[4])
    else:
        print("Usage: python mips_scanner.py <iso_path> <target_name> <target_addr_hex> <output_json>")
        print("Example: python mips_scanner.py MC3.iso on_race_finished 0x003EDAC8 report.json")