# MC3 Archipelago — Complete Reference

*Midnight Club 3: DUB Edition Remix · SLUS-21355 · CRC 0x60A42FF5 · PCSX2 (stock, no fork)*

---

## 1. Architecture (Proven)

```
Python (mc3_api.py)  ←→  PCSX2 Process Memory  ←→  EE RAM  ←→  MC3 Game
        ↑                       ↑                            ↑
   AP WebSocket           Read/WriteProcessMemory      PNACH patches at boot
```

- No PCSX2 fork required — stock PCSX2 v2.6.3 confirmed working
- No ISO patching needed — single `.pnach` file in `cheats/`
- Live injection via `WriteProcessMemory` — no restart between tests
- Save states preserve patches; re-apply mailbox after state load via Python

---

## 2. PNACH File (`cheats/60A42FF5.pnach`)

Minimal safe payload — mailbox only, no hooks:

```
patch=1,EE,00720000,word,4133434D  // "MC3A" magic
patch=1,EE,00720004,word,0000000A  // build_id = 10
patch=1,EE,00720008,word,60A42FF5  // game_crc
patch=1,EE,0072000C,word,00000000  // heartbeat_game
patch=1,EE,00720010,word,00000000  // heartbeat_python
```

Add trampoline hooks for production. Hooks forward to original functions via JALR:

```
// Trampoline pattern (32 instructions each):
//   save ra,s0,s1,t0,t1 on stack
//   do work (increment heartbeat, write event)
//   restore t1,t0,s1,s0
//   load original target into t9, jalr t9
//   restore ra, jr ra
```

---

## 3. Confirmed Memory Map

### Global Pointers

| Label | EE Address | Value | Verified |
|---|---|---|---|
| Profile pointer (pProfile) | `0x00619B14` | `0x007D2310` (varies per save) | ✅ |
| Vehicle list pointer (ppVehList) | `0x006E0170` | `0x007D28B0` | ✅ |
| Vehicle count (pVehCount) | `0x006E0174` | non-scalar (format TBD) | ⚠️ |
| MC3AP Mailbox | `0x00720000` | magic + build_id + CRC | ✅ |

### Vehicle Array

- **Base**: `0x007D28B0` (follows ppVehList)
- **Struct size**: `0x54` bytes (84 bytes)
- **Count**: 32 vehicles loaded at early-game (full 94 unlock with progression)
- **Struct offset 0x00**: pointer to null-terminated ASCII name (e.g. `vp_eclipse_04`)

### Profile

- **Base**: `0x007D2310` (follows pProfile)
- **Money**: NOT found — values near profile are memory alloc sizes (powers of 2). Needs diff test.

### Address Ranges

| EE Range | Contents |
|---|---|
| `0x001A0000` – `0x00715BBC` | ELF code + data (5.7 MB) |
| `0x00619B14` | pProfile |
| `0x006E0170` | ppVehList |
| `0x00720000` | MC3AP mailbox |
| `0x00720010` – `0x007203FF` | Game strings (race names, file paths) |
| `0x0079xxxx` | String table (vehicle names, HUD text) |
| `0x007D2310` | Profile struct |
| `0x007D28B0` | Vehicle array (0x54-byte entries) |

---

## 4. Hook Sites

### Verified JAL Call Sites (safe to hook with trampoline)

| Hook | Patch Addr | Orig Instr | Orig Target | Status |
|---|---|---|---|---|
| OnLoadCareerDataDone | `0x001B0C20` | `0x0C06C624` | `0x001B1890` | ✅ trampoline works |
| SetCarCfg | `0x004AE100` | `0x0C1748E0` | `0x005D2380` | ✅ trampoline works |

### Instruction Patches (NOT JALs — need function entry discovery)

| Label | Address | Original Instr | Type |
|---|---|---|---|
| OnSaveData_1 | `0x001AE8A0` | `0x00000000` | NOP or data |
| OnSaveData_2 | `0x001AF4F8` | `0x27A40030` | `addiu a0, sp, 0x30` |
| OnCreateSavegame | `0x001AF098` | `0xFFBF0078` | `sd ra, 0x78(sp)` |
| OnRaceOver | `0x003EE860` | `0x24050004` | `addiu a1, zero, 4` |
| OnRaceFinished | `0x003EDAC8` | `0x00800008` | `jr a0` |

These 5 are instruction-level patches in MC3CarRandomizer, not JAL call sites. Overwriting them corrupts game behavior. Must discover actual function entry points.

---

## 5. Live API (`tools/mc3_api.py`)

```python
from tools.mc3_api import MC3API

mc3 = MC3API.connect()

# ── Read ────────────────────────────────────────────────────────────────
mc3.profile_ptr             # → 0x007D2310
mc3.vehicle_list_ptr        # → 0x007D28B0
mc3.vehicle_count           # → raw value at 0x006E0174
mc3.vehicles                # → List[Vehicle(name, index, address)]
mc3.mailbox_build_id        # → current build number
mc3.mailbox_heartbeat       # → heartbeat_game counter
mc3.read_u32(ee_addr)       # → int (any EE address)
mc3.read_string(ee_addr)    # → str
mc3.read(ee_addr, size)     # → bytes
mc3.hexdump(ee_addr, 64)    # → formatted string
mc3.snapshot()              # → GameSnapshot dataclass

# ── Write ───────────────────────────────────────────────────────────────
mc3.write_u32(ee_addr, value)    # write 32-bit word
mc3.write(ee_addr, data)         # write raw bytes

# ── Hooks ───────────────────────────────────────────────────────────────
orig = mc3.patch_jal(hook_addr, handler_addr)   # inject live
mc3.restore_jal(hook_addr, orig)                 # revert

# ── Discovery ───────────────────────────────────────────────────────────
snap1 = mc3.snapshot()
# ... perform game action ...
snap2 = mc3.snapshot()
# diff snap1 vs snap2 to find changed values

mc3.close()
```

---

## 6. Tools

| Tool | Purpose |
|---|---|
| `tools/mc3_api.py` | Live modding API (import or run standalone) |
| `tools/probe_memory.py` | Mailbox discovery + status + watch mode |
| `tools/live_inject.py` | CLI for reading/writing EE RAM |
| `tools/mips_assembler.py` | Python MIPS R5900 assembler |
| `tools/build_payload.py` | Generates PNACH from trampoline spec |

### Quick Commands

```bash
# Check mailbox status
python tools/probe_memory.py

# Watch heartbeat (proves hooks fire)
python tools/probe_memory.py --watch

# Live read/write
python tools/live_inject.py status
python tools/live_inject.py read 0x007D2310 256
python tools/live_inject.py write 0x0072000C 0x2A

# Generate PNACH
cd tools && python build_payload.py > E:/Emulator/PCSX2/cheats/60A42FF5.pnach
```

---

## 7. Boot Sequence

```bash
# PCSX2 path:  E:/Emulator/PCSX2/pcsx2-qt.exe
# ISO path:    E:/Emulator/PCSX2/ps2games/MC3.iso
# PNACH path:  E:/Emulator/PCSX2/cheats/60A42FF5.pnach
# Config:      inis/PCSX2.ini → enablecheats = true

# Full boot
E:/Emulator/PCSX2/pcsx2-qt.exe -fastboot E:/Emulator/PCSX2/ps2games/MC3.iso

# Boot from save state (instant, ~15s)
E:/Emulator/PCSX2/pcsx2-qt.exe -fastboot -state 1 E:/Emulator/PCSX2/ps2games/MC3.iso

# Headless (for automated testing)
E:/Emulator/PCSX2/pcsx2-qt.exe -nogui -batch -fastboot E:/Emulator/PCSX2/ps2games/MC3.iso
```

---

## 8. What's Proven

| Capability | Status |
|---|---|
| Stock PCSX2 + PNACH deploys executable MIPS code | ✅ |
| Trampoline hooks forward to original functions | ✅ |
| Game stable with properly-implemented trampolines | ✅ |
| Python reads/writes any EE RAM address | ✅ |
| Live injection without restart | ✅ |
| Save states preserve hook patches | ✅ |
| Vehicle list readable (names, structs) | ✅ |
| Profile pointer readable | ✅ |
| Heartbeat counter works (proves handler execution) | ✅ |

## 9. What's Pending

| Task | Method |
|---|---|
| Find money offset | Diff two snapshots (earn/spend money between them) |
| Find current event ID | Diff snapshots (enter/exit race menu) |
| Find current city | Diff snapshots (travel to new city) |
| Find garage ownership | Diff snapshots (buy a vehicle) |
| Find collectible bitset | Diff snapshots (collect a logo) |
| Find ability flags | Diff snapshots (use Zone/Agro/Roar) |
| Discover function entries for 5 remaining hooks | PCSX2 debugger: read JAL targets at call sites |
| Map full vehicle catalog (94 vehicles) | Progress career further, re-scan |
| Map part catalog | Enter garage part shop, scan memory |
| Map event catalog | Enter race select for each city, scan memory |

---

## 10. Implementation Phases (from Design Doc)

| Phase | Status |
|---|---|
| 0 — Contracts & skeleton | ✅ Complete |
| 1 — Payload foothold (PNACH + mailbox + hooks) | ✅ Complete |
| 2 — Event catalog (stable event IDs) | ⬜ needs diff analysis |
| 3 — Core gates (city, event, vehicle, money) | ⬜ needs found addresses |
| 4 — Full vehicle/garage coverage | ⬜ |
| 5 — Parts/customization coverage | ⬜ |
| 6 — Collectibles and rewards | ⬜ |
| 7 — Polish and release | ⬜ |
