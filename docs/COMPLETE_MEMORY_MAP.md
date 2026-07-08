# MC3 Archipelago — Complete Memory Map & Event Reference

*SLUS-21355 · CRC 0x60A42FF5 · PCSX2 v2.6.3 (stock, no fork)*

---

## Confirmed Memory Map

### Core Game State

| Field | Address | Type | Values | Discovered Via |
|---|---|---|---|---|
| Money | `0x00800870` | u32 | 6600, 8900, 13900 | Diff s1/s5/s14 |
| Money earned | `0x00800874` | u32 | 22000 | Struct neighbor |
| Event catalog ptr | `0x00800878` | u32 ptr | → 0x007C9EF0 | Struct neighbor |
| Profile ptr | `0x00619B14` | u32 ptr | → 0x007D2310 | MC3CarRandomizer |
| Vehicle list ptr | `0x006E0170` | u32 ptr | → 0x007D28B0 | MC3CarRandomizer |
| MC3AP Mailbox | `0x00720000` | struct | "MC3A" + build + CRC | PNACH |

### Race State

| Field | Address | Type | Values | Discovered Via |
|---|---|---|---|---|
| **Live race position** | `0x006BE4F0` | u32 | 1=1st, 3=3rd, 5=5th | Diff s4/s8/s9 |
| Race status flag | `0x007CA10C` | u32 | 1=racing, 2=finished, 3=menu? | Diff s9/s10 |
| Racer array (QS%k) | `0x007CA040` | 6×16B | Starting grid order | Memory scan |
| Race result struct | `0x007CA180` | variable | Populated on finish | Diff s9/s10 |

### Event Catalog

| Field | Address | Type | Notes |
|---|---|---|---|
| Event catalog base | `0x007C9EF0` | struct array | 16-byte entries with ASCII tags |

### Vehicle Catalog

| Field | Address | Type | Notes |
|---|---|---|---|
| Vehicle array base | `0x007D28B0` | struct array | 0x54-byte entries, 32-94 vehicles |
| Struct +0x00 | name_ptr → string | u32 | e.g. vp_eclipse_04 |
| Struct size | 0x54 (84 bytes) | — | Confirmed for early-game |

### Profile Area

| Field | Offset from profile | Type | Notes |
|---|---|---|---|
| Profile base | `0x007D2310` | struct | Follows 0x00619B14 |
| Race count | +0x18 | u32 | 1→7 (s1→s5) |
| Progress % | +0x40 | u32 | 8→100 (s1→s5) |
| Racer completion array | +0x114 | 6 entries | 0x2C bytes each |

### Hook Sites

| Hook | Patch Addr | Type | Orig Instr | Safe Candidate | Confidence |
|---|---|---|---|---|---|
| OnLoadCareerDataDone | `0x001B0C20` | JAL call site | `0x0C06C624` → `0x001B1890` | Direct trampoline | 1.0 |
| SetCarCfg | `0x004AE100` | JAL call site | `0x0C1748E0` → `0x005D2380` | Direct trampoline | 1.0 |
| OnCreateSavegame | `0x001AF098` | **IS a JAL** | `0x0C06C506` → `0x001B1418` | Direct trampoline | 0.80 |
| OnRaceFinished | `0x003EDAC8` | jr a0 dispatch | — | `0x004A8328` (caller JAL) | 0.60 |
| OnRaceOver | `0x003EE860` | addiu a1,zero,4 | — | `0x003D6AAC` (caller JAL) | 0.65 |
| OnSaveData_1 | `0x001AE8A0` | nop | — | `0x001A2434` (caller JAL) | 0.55 |
| OnSaveData_2 | `0x001AF4F8` | addiu a0,sp,0x30 | — | `0x001AF058` (caller JAL) | 0.55 |

---

## Suspected Fields (Needs Confirmation)

| Field | Candidate Address | Evidence | To Confirm |
|---|---|---|---|
| Collectible bitset | `0x00618D24`, `0x00621708` | Bitfield changed s6→s13 | Collect 2nd logo, verify bit change |
| Garage ownership | `0x00618AD8`, `0x006145FC` | 0→1 on purchase | Buy 2nd car, verify flag |
| Tournament win flag | `0x00615A3C` | 0→1 after tournament | Win another tournament |
| Vehicle purchased flag | `0x00618AD8` | 0→1 post-purchase | Confirm with different car |
| Current city | Not found | — | Need city travel state |
| Current event ID | Not found | — | Need different event prompt |
| Part catalog | Not found | — | Need part shop state |

---

## Event Detection

### Race Completion
- **Watch:** `0x007CA10C` changes from 1 → 2
- **Watch:** `0x006BE4F0` changes from 1-6 → (race ends, value resets)
- **Result:** race position stored in result struct at `0x007CA180`

### Collectible Pickup
- **Watch:** Candidate bitfields at `0x00618D24`, `0x00621708`
- **Method:** Poll these bitfields; any bit change = collectible picked up
- **To ID which collectible:** Need to map which bit = which logo

### Vehicle Purchase
- **Watch:** Money at `0x00800870` decreases
- **Watch:** `0x00618AD8` flag changes
- **Method:** Detect money decrease + flag change simultaneously

### Money Change (any reason)
- **Watch:** `0x00800870` changes
- **Delta:** New value - old value = amount earned/spent

---

## Save States

| # | Description | Money | Key Feature |
|---|---|---|---|
| 1 | Post-tutorial free roam | $6,600 | Baseline |
| 2 | Vanessa prompt | $6,600 | Event start gate |
| 3 | Before race trigger | $6,600 | Race start |
| 4 | Before finish, 1st | $7,300 | Win detection |
| 5 | Post-Vanessa, club unlocks | $8,900 | Progression |
| 6 | Post-everything, map screen | $8,900 | Full state |
| 8 | Before finish, 3rd | $6,680 | Position verify |
| 9 | Mid-race, 5th | — | Position verify |
| 10 | Post-race, 5th | — | Race finish flag |
| 11 | Post-restart from s9 | — | Reset behavior |
| 12 | Garage | $6,600 | Garage state |
| 13 | s6 + 1 collectible | $8,900 | Collectible bitset |
| 14 | s13 + Lexus + tournament | $13,900 | Purchase + tournament |
| 15 | High-level garage | $13,900 | Garage menu |
| 16 | Car purchase menu | $13,900 | Dealer state |

---

## Architecture Status

| Capability | Status |
|---|---|
| Stock PCSX2 + PNACH deploys MIPS code | ✅ |
| Trampoline hooks (2 verified, 1 discovered) | ✅ |
| Python reads/writes any EE address | ✅ |
| Live injection without restart | ✅ |
| Race position detection (1st/3rd/5th) | ✅ |
| Race completion detection (status flag) | ✅ |
| Money read/write/delta detection | ✅ |
| Vehicle list readable | ✅ |
| Collectible detection | ⚠️ candidate found |
| Garage ownership | ⚠️ candidate found |
| Current city | ❌ |
| Current event ID | ❌ |

---

## Tools

| Tool | Command | Purpose |
|---|---|---|
| Watch | `python watch.py [interval]` | Live game state poller |
| Action API | `from action_driver import MC3LiveAPI` | Read/write game state |
| Explorer | `python run_explore.py explore N` | Memory dump + scan |
| Probe | `python probe_memory.py` | Mailbox health check |
| Injects | `python live_inject.py` | Raw memory R/W |
| Assembler | `python mips_assembler.py` | MIPS code generation |
| Scanner | `python mips_scanner.py` | Static ELF analysis |
