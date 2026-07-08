# MC3 Archipelago — Complete Memory Map & Status

*SLUS-21355 · CRC 0x60A42FF5 · PCSX2 v2.6.3 (stock, no fork) · 2026-07-06*

---

## 1. Confirmed Memory Map

### Game State (Read/Write Verified)

| # | Field | EE Address | Size | Format | Proof | States |
|---|---|---|---|---|---|---|
| 1 | **Money** | `0x00800870` | u32 | raw integer | Write/read roundtrip | s1=$6,600 s5=$8,900 |
| 2 | Money earned (total?) | `0x00800874` | u32 | raw integer | Constant 22,000 | s1-s5 |
| 3 | Event catalog pointer | `0x00800878` | u32 | → `0x007C9EF0` | Followed pointer chain | all |
| 4 | **Player race position** | `0x007CA044` | u32 | 1=1st, 3=3rd | Diff s4 vs s8 | s4=1 s8=3 |
| 5 | Profile pointer | `0x00619B14` | u32 | → `0x007D2310` | MC3CarRandomizer + verified | all |
| 6 | Vehicle list pointer | `0x006E0170` | u32 | → `0x007D28B0` | MC3CarRandomizer + verified | all |
| 7 | Vehicle list count | `0x006E0174` | u32 | non-simple (format TBD) | MC3CarRandomizer | all |
| 8 | Mailbox base | `0x00720000` | struct | magic "MC3A" + build_id + CRC | PNACH write verified | all |

### Race State

| # | Field | EE Address | Size | Format | Proof |
|---|---|---|---|---|---|
| 9 | Racer position array | `0x007CA040` | 6×16 bytes | QS%k entries | Mapped all 6 |
| 10 | Racer entry: tag | `+0x00` | u32 | `0x6B255351` ("QS%k") | Constant |
| 11 | Racer entry: position | `+0x04` | u32 | 1-6 (player is entry 0) | Diff-verified |
| 12 | Racer entry: counter | `+0x08` | u32 | ~1,736,226 (lap timer?) | Observed |
| 13 | Racer entry: status | `+0x0C` | u32 | 0 during race, changes at end | Observed |

### Event Catalog (`0x007C9EF0`)

16-byte entries. Discovered entries:

| Index | Address | Tag | idx | v8 | va | vc (s1→s5) | Likely Meaning |
|---|---|---|---|---|---|---|---|
| 0 | `0x007C9EF0` | LOCc | 0 | 0x7E21 | 0x001A | 0→0 | Location/map entry |
| 1 | `0x007C9F00` | LOCc | 1 | 0x7E21 | 0x001A | 0→0 | Location/map entry |
| 2 | `0x007C9F10` | LOCc | 2 | 0x7E21 | 0x001A | 0→0 | Location/map entry |
| 3 | `0x007C9F20` | SDkc | 0 | 0x3A00 | 0x007D | float→float | San Diego k... |
| 4 | `0x007C9F30` | POHg | 0 | 0x0001 | 0x0000 | 3→? | ??? |
| 5 | `0x007C9F40` | RPHg | 0 | 0x1E41 | 0x004F | 6→5 | ??? |
| 6 | `0x007C9F50` | CTMg | 0 | 0xF581 | 0x3F79 | 7→35 | Completion counter? |
| 7 | `0x007C9F60` | NIWg | 0 | 0x8381 | 0x001A | 1→? | ??? |
| 8 | `0x007C9F70` | PThg | 0 | 0x7E00 | 0x001A | float→? | ??? |
| 9 | `0x007C9F80` | SDkg | 0 | 0x3A00 | 0x007D | float→float | San Diego k... |
| 10 | `0x007C9F90` | STvg | 0 | 0x0010 | 0x0000 | float→? | ??? |
| 11-15 | `0x007C9FA0+` | EC$k... | 0 | varies | 0x001A | varies | ??? |

### Profile Struct (`0x007D2310`)

| Offset | Value (s5) | Changed s1→s5? | Likely Meaning |
|---|---|---|---|
| +0x00 | 0 | no | magic/version |
| +0x04 | 0 | 1→0 | tutorial_complete flag |
| +0x0C | 4 | no | constant |
| +0x10 | 4 | no | constant |
| +0x14 | 1 | no | flag |
| +0x18 | 7 | 1→7 | **race completions count** |
| +0x2C | 5 | no | flag |
| +0x3C | 1 | no | flag |
| +0x40 | 100 | 8→100 | **progress percentage?** |
| +0x68-0x90 | ASCII string | — | file path: `...order\easy\sd_race\...` |

Racer completion array at +0x114 (6×0x2C-byte entries):
| Entry | Offset | ptr | flags |
|---|---|---|---|
| 0 | +0x114 | 0x007D2700 | 1,1,1 |
| 1 | +0x140 | 0x0079FF30 | 1,1,1 |
| 2 | +0x16C | 0x007D3340 | 1,?-1 |
| 3 | +0x198 | 0x007D3460 | 1,?-1 |
| 4 | +0x1C4 | 0x007D3580 | 1,?-1 |
| 5 | +0x1F0 | 0x007D36A0 | 1,?-1 |

### Game State Table (`0x00717000`)

8×32-byte entries. Entry 0:
| Offset | Value | Meaning |
|---|---|---|
| +0x00 | 0x00717040 | ptr to data |
| +0x04 | 0x0079FE60 | ptr to metadata |
| +0x08 | 0x00010B04 | flags |
| +0x0C | 0x00717020 | ptr to string ("city_window.shadert") |
| +0x10 | 2 | count |
| +0x14 | 0x007C9EF0 | **ptr to event catalog** |
| +0x18 | 0x007CA6F0 | ptr (uninitialized in prompt state) |

### Vehicle Array (`0x007D28B0`)

- **Struct stride**: `0x54` (84 bytes) — best fit, 32 vehicles found at early-game
- **Full catalog**: 94 vehicles (Remix), more populate as game progresses
- **Struct offset 0x00**: pointer to vehicle name string
- **Discovered vehicles** (first 5): vp_eclipse_04, vp_golfr32_04, vp_impala_64, vp_chrysler300c_05, vp_lancer_04

### Mailbox (`0x00720000`)

| Offset | Field | Value |
|---|---|---|
| +0x00 | magic | "MC3A" |
| +0x04 | build_id | 10 |
| +0x08 | game_crc | 0x60A42FF5 |
| +0x0C | heartbeat_game | 0 |
| +0x10 | heartbeat_python | 0 |

---

## 2. Hook Sites

### Verified JAL Call Sites (Safe to Hook with Trampoline)

| Hook | Patch Addr | Orig Instr | Orig Target | Status |
|---|---|---|---|---|
| OnLoadCareerDataDone | `0x001B0C20` | `0x0C06C624` | `0x001B1890` | ✅ Trampoline works |
| SetCarCfg | `0x004AE100` | `0x0C1748E0` | `0x005D2380` | ✅ Trampoline works |

### Instruction Patches (NOT JALs — Function Entries Found via Automated Static Analysis)

| Label | Address | Orig Instr | Safe Hook Candidate | Kind | Confidence |
|---|---|---|---|---|---|
| OnSaveData_1 | `0x001AE8A0` | `0x00000000` (NOP) | `0x001A2434` | caller JAL trampoline | 0.55 |
| OnSaveData_2 | `0x001AF4F8` | `0x27A40030` | `0x001AF058` | caller JAL trampoline | 0.55 |
| OnCreateSavegame | `0x001AF098` | `0x0C06C506` → JAL `0x001B1418` | `0x001AF098` | **IS a JAL — direct trampoline** | 0.80 |
| OnRaceOver | `0x003EE860` | `0x24050004` | `0x003D6AAC` | caller JAL trampoline | 0.65 |
| OnRaceFinished | `0x003EDAC8` | `0x00800008` (jr a0) | `0x004A8328` | caller JAL trampoline | 0.60 |

All 5 discovered via automated MIPS static analysis (62,812 JALs, 12,124 functions). **0 targets require PCSX2 GUI debugger.** Stage 3 dynamic probing pending to validate candidates.

---

## 3. Save States

| # | Description | Money | Key Feature |
|---|---|---|---|
| 1 | Post-tutorial free roam (San Diego) | $6,600 | Profile baseline |
| 2 | Vanessa challenge prompt ("Press O") | $6,600 | Event start gate test |
| 3 | Right before race start trigger | $6,600 | Mid-race state |
| 4 | Before finish line, 1st place | $7,300 | Win detection |
| 5 | After all 3 Vanessa races, club unlocks | $8,900 | Progression diff baseline |
| 6 | After everything loaded post-last-race | ? | Full state |
| 8 | Before finish line, 3rd place | $6,680 | Loss detection |

---

## 4. Blocked Items

### Need Save States From User (3 items)

| # | Unknown Field | Save State Needed | Why Blocked |
|---|---|---|---|
| 1 | **Current city** (city ID, unlock flags) | Free roam in Atlanta or Detroit | No save state exists outside San Diego — can't diff to find city identifier in memory |
| 2 | **Garage ownership** (vehicle ownership array) | Garage with 2-3 owned vehicles, vehicle select screen open | No multi-vehicle garage save state — can't find ownership struct |
| 3 | **Current event ID** (which race is selected) | Event prompt for a DIFFERENT event than Vanessa (tournament, club race, or different street racer) | Vanessa prompt vs free roam diff showed 0 changes in event catalog — need a second event type to find the selector |

### Need PCSX2 Debugger (0 items)

All 5 previously-blocked hook sites now have automated candidates via MIPS static analysis.
Stage 3 dynamic probing (live validation) remaining — but no GUI debugger required.

| # | Hook | Candidate | Next Step |
|---|---|---|---|
| 4 | OnSaveData_1 | `0x001A2434` (caller JAL) | Dynamic probe on save state |
| 5 | OnSaveData_2 | `0x001AF058` (caller JAL) | Dynamic probe on save state |
| 6 | OnCreateSavegame | `0x001AF098` (IS a JAL) | Dynamic probe on save state |
| 7 | OnRaceOver | `0x003D6AAC` (caller JAL) | Dynamic probe on state 4 |
| 8 | OnRaceFinished | `0x004A8328` (caller JAL) | Dynamic probe on state 4 |

### Cannot Do Without Game Progression (2 items)

| # | Field | Why Blocked |
|---|---|---|
| 9 | Class unlock flags (D/C/B/A) | Need to progress career to unlock each class, diff before/after |
| 10 | Part catalog | Need access to part shop with multiple categories unlocked |

---

## 5. Architecture Proven

| Capability | Status |
|---|---|
| Stock PCSX2 + PNACH deploys executable MIPS code | ✅ |
| Trampoline hooks forward to original functions | ✅ |
| Game stable with proper trampolines | ✅ |
| Python reads/writes any EE RAM address | ✅ |
| Live injection without PCSX2 restart | ✅ |
| Save states preserve hook patches | ✅ |
| Money write/read roundtrip to game memory | ✅ |
| Player race position detected | ✅ |
| Vehicle list + names readable | ✅ |

---

## 6. Tools Built

| Tool | Purpose |
|---|---|
| `tools/mc3_api.py` | Live modding API (import or CLI) |
| `tools/probe_memory.py` | Mailbox discovery + status + watch |
| `tools/live_inject.py` | CLI for EE RAM read/write/patch |
| `tools/mips_assembler.py` | Python MIPS R5900 assembler |
| `tools/build_payload.py` | PNACH generator from trampoline spec |
| `tools/run_explore.py` | Automated exploration: boot, snapshot, diff |

### Quick Commands

```bash
# Check mailbox status
python tools/probe_memory.py

# Live read/write any EE address
python tools/live_inject.py write 0x00800870 9999   # set money to $9,999
python tools/live_inject.py read 0x007CA044          # read race position
python tools/live_inject.py patch 0x004AE100 0x0C1748E0  # restore original JAL

# Exploration
python tools/run_explore.py boot 1     # boot save state 1
python tools/run_explore.py explore 1  # explore save state 1
python tools/run_explore.py diff s1.json s5.json  # diff two snapshots

# API
python -c "from tools.mc3_api import MC3API; mc3=MC3API.connect(); print(mc3.vehicles)"
```

### Boot Sequences

```bash
# PCSX2: E:/Emulator/PCSX2/pcsx2-qt.exe
# ISO:   E:/Emulator/PCSX2/ps2games/MC3.iso
# PNACH: E:/Emulator/PCSX2/cheats/60A42FF5.pnach
# Config: inis/PCSX2.ini → enablecheats = true

# Full boot
E:/Emulator/PCSX2/pcsx2-qt.exe -fastboot E:/Emulator/PCSX2/ps2games/MC3.iso

# Boot from save state (~15s)
E:/Emulator/PCSX2/pcsx2-qt.exe -fastboot -state 1 E:/Emulator/PCSX2/ps2games/MC3.iso

# Headless (for automated testing)
E:/Emulator/PCSX2/pcsx2-qt.exe -nogui -batch -fastboot E:/Emulator/PCSX2/ps2games/MC3.iso
```

---

## 7. Project Files

| Path | Purpose |
|---|---|
| `docs/REFERENCE.md` | Architecture + API reference |
| `docs/design.md` | Full design doc (stock PCSX2 + upstream compliance) |
| `docs/memory_map.md` | Earlier memory map (superseded by this document) |
| `docs/pcsx2_stock_research.md` | Stock PCSX2 payload research |
| `docs/reverse_engineering_checklists.md` | RE graduation checklists |
| `D:/Development/archipelago/mc3/mc3-ap/snapshot_state*.json` | Full memory snapshots |
| `D:/Development/archipelago/mc3/mc3-ap/full_snap*.json` | Full EE RAM dumps |
