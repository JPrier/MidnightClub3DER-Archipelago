# MC3 Memory Map & Modding API Reference

*SLUS-21355 / CRC 0x60A42FF5 — Midnight Club 3: DUB Edition Remix (NTSC-U)*

---

## Confirmed Addresses

| Label | EE Address | Type | Value | Verified |
|---|---|---|---|---|
| `pProfile` | `0x00619B14` | pointer | `0x007D2310` | ✅ |
| `ppVehList` | `0x006E0170` | pointer | `0x007D28B0` | ✅ |
| `pVehCount` | `0x006E0174` | unknown | `6291550` (not a simple count) | ⚠️ format TBD |
| Mailbox base | `0x00720000` | struct | `MC3A` + build + CRC | ✅ |

## Verified Hook Sites

| Hook | Address | Type | Original Instruction | Target |
|---|---|---|---|---|
| OnLoadCareerDataDone | `0x001B0C20` | JAL call site | `0x0C06C624` | `0x001B1890` |
| SetCarCfg | `0x004AE100` | JAL call site | `0x0C1748E0` | `0x005D2380` |
| OnSaveData_1 | `0x001AE8A0` | INSTRUCTION (not JAL) | `0x00000000` | ⚠️ needs function entry |
| OnSaveData_2 | `0x001AF4F8` | INSTRUCTION (not JAL) | `0x27A40030` | ⚠️ needs function entry |
| OnCreateSavegame | `0x001AF098` | INSTRUCTION (not JAL) | `0xFFBF0078` | ⚠️ needs function entry |
| OnRaceOver | `0x003EE860` | INSTRUCTION (not JAL) | `0x24050004` | ⚠️ needs function entry |
| OnRaceFinished | `0x003EDAC8` | INSTRUCTION (not JAL) | `0x00800008` | ⚠️ needs function entry |

## Vehicle Array

- **Base**: `0x007D28B0`
- **Struct size**: `0x70` bytes (112 bytes per vehicle)
- **Vehicles discovered**: 24 (of 94 total — more populate as game progresses?)
- **Struct layout** (partial):
  ```
  +0x00: name_ptr (pointer to null-terminated ASCII name)
  +0x04: unknown (usually 0)
  +0x08: unknown (usually 0)
  +0x0C: unknown (flags? 0x0D seen)
  ```

**First 5 vehicles discovered:**
| Index | Address | Name |
|---|---|---|
| 0 | `0x007D28B0` | `vp_eclipse_04` (Mitsubishi Eclipse) |
| 1 | `0x007D2920` | `vp_hummer_02` (Hummer H2) |
| 2 | `0x007D2990` | `vp_skyline_02` (Nissan Skyline) |
| 3 | `0x007D2A00` | (next vehicle) |
| 4 | `0x007D2A70` | (next vehicle) |

## Profile Structure

- **Pointer at**: `0x00619B14` → `0x007D2310`
- **Fields identified** (partial):
  ```
  +0x000: unknown (0)
  +0x004: unknown (1) — flag?
  +0x008: unknown (0)
  +0x00C: unknown (4)
  +0x010: unknown (4)
  +0x014: unknown (1)
  +0x018: unknown (1)
  ```
- **Money**: NOT confirmed. Values in 500-32768 range near profile are likely memory alloc sizes (powers of 2). Need differential analysis — save state, spend/earn money, compare memory.

## Address Space Map

| EE Range | Contents |
|---|---|
| `0x001A0000`-`0x00715BBC` | ELF executable (loadable segment, 5.7MB) |
| `0x00619B14` | Profile pointer |
| `0x006E0170` | Vehicle list pointer |
| `0x00720000` | MC3AP mailbox |
| `0x00720010`-`0x007203FF` | Game string data (race names, file paths) |
| `0x007D2310` | Profile data |
| `0x007D28B0` | Vehicle array (0x70-byte structs) |
| `0x0079xxxx` | String table (vehicle names, HUD text) |

## TODO: Values Needing Differential Analysis

These require comparing memory before/after a game action:

| Action | What to Find |
|---|---|
| Earn/spend money | Money offset in profile |
| Enter race menu | Current event ID / event pointer |
| Travel to new city | Current city ID |
| Buy a vehicle | Garage ownership array |
| Collect a logo | Collectible bitset |
| Use Zone ability | Ability activation flag |
| Unlock a city | City unlock flags |

## API Usage

```python
from tools.mc3_api import MC3API

mc3 = MC3API.connect()

# Read game state
profile = mc3.profile_ptr          # 0x007D2310
vehicles = mc3.vehicles             # List[Vehicle]

# Read raw memory
data = mc3.read(0x007D2310, 256)

# Write memory
mc3.write_u32(0x007D2310, 42)

# Patch a hook live
orig = mc3.patch_jal(0x001B0C20, 0x00720040)  # redirect to our handler
mc3.restore_jal(0x001B0C20, orig)              # restore original

# Read vehicle names
for v in mc3.vehicles:
    print(v.name)
```
