"""Phase 1b payload — trampoline hooks that forward to original functions.

Key insight from ELF analysis: only 2 of the 7 MC3CarRandomizer "call sites"
are actual JAL instructions. The other 5 are regular instructions — overwriting
them breaks game behavior (e.g., the save-stuck screen).

This payload:
  1. Hooks SetCarCfg (JAL 0x005D2380) and OnLoadCareerDataDone (JAL 0x001B1890)
  2. Each handler: save RA, increment heartbeat, write event, restore RA
  3. Forward to original function via JALR (trampoline)
  4. Original returns to our handler, we JR RA to the original caller
"""

import struct
from mips_assembler import MIPSAssembler, R

MAILBOX_EE_ADDR = 0x00720000
OFF_HB_GAME = 0x0C
OFF_HB_PYTHON = 0x10

# Events
EVT_PROFILE_LOADED = 0x01
EVT_CAR_CONFIG = 0x04

# Verified JAL call sites with their original targets
HOOKS = [
    (0x001B0C20, "hook_career_load", 0x001B1890, EVT_PROFILE_LOADED, "OnLoadCareerDataDone"),
    (0x004AE100, "hook_car_cfg",      0x005D2380, EVT_CAR_CONFIG,     "SetCarCfg"),
]


def _build_trampoline_handler(asm, label, original_target, event_type):
    """Build a handler that:
    1. Saves registers
    2. Increments heartbeat + writes event
    3. Calls original function via JALR (so original returns to us)
    4. Restores caller's RA and returns
    """
    asm.lbl(label)

    # Prologue — save caller's RA and work registers
    asm.addiu(R.SP, R.SP, -32)
    asm.sw(R.RA, R.SP, 0)
    asm.sw(R.S0, R.SP, 4)
    asm.sw(R.S1, R.SP, 8)
    asm.sw(R.T0, R.SP, 12)
    asm.sw(R.T1, R.SP, 16)

    # Increment heartbeat
    asm.lui(R.T0, 0x0072)
    asm.lw(R.T1, R.T0, OFF_HB_GAME)
    asm.addiu(R.T1, R.T1, 1)
    asm.sw(R.T1, R.T0, OFF_HB_GAME)

    # Write event type to debug area (offset 0x50, above game string data at 0x10-0x3F)
    asm.lui(R.T0, 0x0072)
    asm.ori(R.T0, R.T0, 0x0300)
    asm.lui(R.T1, 0x0000)
    asm.ori(R.T1, R.T1, event_type)
    asm.sw(R.T1, R.T0, 0)

    # Write timestamp (heartbeat) to debug area + 8
    asm.lui(R.T0, 0x0072)
    asm.lw(R.T1, R.T0, OFF_HB_GAME)
    asm.lui(R.T0, 0x0072)
    asm.ori(R.T0, R.T0, 0x0308)
    asm.sw(R.T1, R.T0, 0)

    # Restore work registers (but NOT RA — we need caller's RA later)
    asm.lw(R.T1, R.SP, 16)
    asm.lw(R.T0, R.SP, 12)
    asm.lw(R.S1, R.SP, 8)
    asm.lw(R.S0, R.SP, 4)

    # Call original function via JALR (sets RA = next_instr in handler)
    asm.load_imm(R.T9, original_target)
    asm.jalr(R.T9)
    asm.nop()

    # Back from original. RA = next_instr (set by JALR above)
    # Restore caller's RA and return
    asm.lw(R.RA, R.SP, 0)     # restore caller's RA
    asm.addiu(R.SP, R.SP, 32)
    asm.jr(R.RA)
    asm.nop()


def build_payload():
    asm = MIPSAssembler(base=0x00720040)

    for hook_addr, label, orig_target, evt_type, name in HOOKS:
        _build_trampoline_handler(asm, label, orig_target, evt_type)

    binary = asm.link()

    # ── Generate PNACH ──────────────────────────────────────────────────
    lines = [
        "// MC3AP Phase 1b — Trampoline Hooks",
        f"// {len(asm._instructions)} instructions, {len(binary)} bytes at 0x00720040",
        "//",
        "// Verified JAL call sites (from ELF analysis):",
    ]
    for hook_addr, label, orig_target, evt_type, name in HOOKS:
        lines.append(f"//   {name} at 0x{hook_addr:08X} -> JAL 0x{orig_target:08X} (original)")

    lines.extend([
        "//",
        "// Each handler: save regs -> heartbeat++ -> write event ->",
        "//                JALR original_func -> restore ra -> jr ra",
        "",
        "// --- Mailbox header ---",
        "patch=1,EE,00720000,word,4133434D // 'MC3A' magic",
        "patch=1,EE,00720004,word,00000008 // build_id = 7",
        "patch=1,EE,00720008,word,60A42FF5 // game_crc = 0x60A42FF5",
        "patch=1,EE,0072000C,word,00000000 // heartbeat_game = 0",
        "patch=1,EE,00720010,word,00000000 // heartbeat_python",
        "",
        "// --- Payload code at 0x00720040 ---",
    ])

    for i in range(0, len(binary), 4):
        word = struct.unpack("<I", binary[i:i + 4])[0]
        addr = 0x00720040 + i
        instr_idx = i // 4
        mnem = asm._instructions[instr_idx].mnemonic if instr_idx < len(asm._instructions) else ""
        lbl = ""
        for name, laddr in asm._labels.items():
            if laddr == addr:
                lbl = f"  <-- {name}"
        lines.append(f"patch=1,EE,{addr:08X},word,{word:08X} // {mnem}{lbl}")

    lines.append("")
    lines.append("// --- Hook patches (JAL to trampoline handlers) ---")
    for hook_addr, label, orig_target, evt_type, name in HOOKS:
        handler_addr = asm._labels[label]
        jal_encoded = 0x0C000000 | ((handler_addr >> 2) & 0x03FFFFFF)
        lines.append(
            f"patch=1,EE,{hook_addr:08X},word,{jal_encoded:08X} "
            f"// JAL 0x{handler_addr:08X} ({name}) — forwards to 0x{orig_target:08X}"
        )

    return binary, lines


if __name__ == "__main__":
    binary, lines = build_payload()
    print("\n".join(lines))
    print(f"\n// Total: {len(binary)} bytes, {len(lines)} PNACH directives")