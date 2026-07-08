# MC3StockPCSX2 Payload Research

SLUS_213.55 / CRC 0x60A42FF5 / ELF at sector 544, vaddr 0x001A0000

## 1. Safe Memory Regions

EE RAM layout (32MB main RAM, 0x00000000 - 0x01FFFFFF):
- 0x001A0000 - 0x00663674: ELF filesz (5075060 bytes)
- 0x001A0000 - 0x0071627C: ELF memsz (5725500 bytes)
- Known game pointers: ppVehList=0x006E0170, pProfile=0x00619B14

**Candidate payload base: 0x00710000** (above memsz end, 4KB-aligned)
Need to validate: write test values and check they persist across game execution.

## 2. Approach A: PNACH-Only Code Injection

### Capability
PNACH writes raw MIPS instructions to EE RAM at boot.
We can write an entire payload binary as a series of word patches.

### Steps
1. Compile payload C code to MIPS binary (PS2 EE GCC)
2. Convert binary to PNACH word-patch directives
3. Generate JAL patches for each hook site
4. Python client discovers mailbox via known address + magic scan

### Limits
- No background execution (all code triggered by hooks only)
- Must fit in chosen memory region
- Hook code must handle register save/restore
- Debugging requires PCSX2 debugger or memory inspection

### Feasibility: HIGH
PNACH can inject ~dozens of KB of code. Our payload needs ~4KB.

## 3. Approach B: ISO ELF Patching (Backup)

### When Needed
If PNACH cannot provide:
- Persistent code across savestates
- Sufficient space in a safe region
- Reliable execution when game writes over our region

### Implementation
Python tool that:
1. Extracts SLUS_213.55 from ISO
2. Appends payload to end of .text segment (increase memsz)
3. Patches hook call sites with JAL to payload
4. Rebuilds ISO

### User Flow
User runs `mc3ap_patch_iso.py` once, gets a patched ISO.

## 4. Test Plan

### Test 1: Memory Region Validation
- Write PNACH that sets 0x00710000 to known pattern
- Boot game, play 5 min, read memory with Python
- Verify pattern survived (no game overwrite)

### Test 2: Hook Injection
- Write minimal payload at 0x00710000
- Patch known hook (OnLoadCareerDataDone @ 0x1B0C20)
- Boot game, load career, read memory for our marker

### Test 3: Heartbeat
- Write payload that increments counter each frame
- Python verifies counter changes and timestamp advances

### Test 4: Full Mailbox
- Implement mailbox struct in EE RAM
- Test command/event ring buffer round trip
- Verify Python can discover, read, and write

## 5. Files to Create

```
cheats/60A42FF5.pnach       # Boot-time payload + hook patches
tools/generate_pnach.py      # Converts payload .bin to PNACH directives
tools/probe_memory.py        # Python memory scanner for PCSX2
tools/validate_region.py     # Tests memory region safety
```