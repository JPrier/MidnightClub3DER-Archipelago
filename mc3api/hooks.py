"""Live hook management — patch/restore JAL call sites in game code.

Only VERIFIED JAL call sites may be trampolined (see memmap hook tuples).
Instruction-level sites (jr/addiu/etc.) must go through hook discovery first;
overwriting them corrupts game behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


JAL_OPCODE = 0x03


def encode_jal(target: int) -> int:
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


def decode_jal(instr: int) -> Optional[int]:
    """Return the JAL target address, or None if not a JAL."""
    if (instr >> 26) & 0x3F != JAL_OPCODE:
        return None
    return (instr & 0x03FFFFFF) << 2


@dataclass
class HookHandle:
    patch_addr: int
    original_instr: int
    handler_addr: int


class HookManager:
    """Patch verified JAL call sites to jump into payload trampolines."""

    def __init__(self, bridge):
        self._bridge = bridge
        self._active: dict[int, HookHandle] = {}

    def install(self, patch_addr: int, handler_addr: int,
                expected_original: Optional[int] = None) -> HookHandle:
        """Redirect the JAL at patch_addr to handler_addr.

        If expected_original is given, refuses to patch when the current
        instruction doesn't match (protects against double-patching or
        wrong-build addresses).
        """
        current = self._bridge.read_u32(patch_addr)
        if expected_original is not None and current != expected_original:
            if decode_jal(current) == handler_addr:
                raise RuntimeError(f"0x{patch_addr:08X} already hooked to 0x{handler_addr:08X}")
            raise RuntimeError(
                f"instruction mismatch at 0x{patch_addr:08X}: "
                f"expected 0x{expected_original:08X}, found 0x{current:08X}")
        if decode_jal(current) is None:
            raise RuntimeError(f"0x{patch_addr:08X} is not a JAL (0x{current:08X}) — refusing to patch")

        self._bridge.write_u32(patch_addr, encode_jal(handler_addr))
        handle = HookHandle(patch_addr, current, handler_addr)
        self._active[patch_addr] = handle
        return handle

    def restore(self, handle: HookHandle):
        self._bridge.write_u32(handle.patch_addr, handle.original_instr)
        self._active.pop(handle.patch_addr, None)

    def restore_all(self):
        for handle in list(self._active.values()):
            self.restore(handle)
