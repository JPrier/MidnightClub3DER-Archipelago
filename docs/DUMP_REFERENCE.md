# Memory Dump Reference

## Location

```
D:\Development\archipelago\mc3\mc3-ap\dumps\
```

## Directory Structure

```
dumps/
  s1_free_roam/
    snap_000.json    # Baseline snapshot (snapshot 1)
    snap_001.json    # Snapshot 2 (1 second later)
    snap_002.json    # Snapshot 3 (2 seconds later)
    snap_003.json    # Snapshot 4
    snap_004.json    # Snapshot 5
    diff_000_001.json # Changes between snap 0 and snap 1
    diff_001_002.json # Changes between snap 1 and snap 2
    diff_002_003.json # ...
    diff_003_004.json

  s2_event_prompt/   # Same structure
  s3_race_start/
  s4_race_finish_1st/
  s5_post_vanessa/
  s10_post_race/
  s12_garage/
  s13_collectible/
  s14_tournament_lexus/
```

## File Formats

### snap_NNN.json — Full EE RAM Snapshot

A JSON object mapping 64KB chunk start addresses to hex strings.

```json
{
  "00600000": "4d4333410a000000f52fa460...",
  "00610000": "0000000001000000...",
  ...
  "01FF0000": "0000000000000000..."
}
```

- **512 chunks** per snapshot (32MB of 64KB each)
- Each chunk is 131,072 hex characters (65,536 bytes)
- Address `00600000` = EE RAM offset 0x00600000
- Only modified regions contain non-zero data

### diff_NNN_MMM.json — Changed Dwords Between Snapshots

A JSON array of `[address_hex, old_value, new_value]` entries.

```json
[
  ["0x006BE4F0", 3, 4],
  ["0x00800870", 6600, 7300],
  ["0x007CA10C", 1, 2]
]
```

- **Address**: EE RAM address where change occurred
- **Old value**: u32 value in the earlier snapshot
- **New value**: u32 value in the later snapshot

## Save States

| Directory | Save State | Description | Money |
|---|---|---|---|
| s1_free_roam | Slot 1 | Post-tutorial free roam, San Diego | $6,600 |
| s2_event_prompt | Slot 2 | Vanessa challenge "Press O" prompt | $6,600 |
| s3_race_start | Slot 3 | Race start trigger | $6,600 |
| s4_race_finish_1st | Slot 4 | Just before finish, 1st place | $7,300 |
| s5_post_vanessa | Slot 5 | All 3 Vanessa races done, club unlocks | $8,900 |
| s10_post_race | Slot 10 | After race, 5th place, result screen | — |
| s12_garage | File | Garage with Scion tC | $6,600 |
| s13_collectible | File | s6 + 1 Rockstar logo collected | $8,900 |
| s14_tournament_lexus | File | s13 + Lexus IS300 + tournament win | $13,900 |

## Volatility by State

Changes per second between snapshots. Higher = more game activity.

| State | ~Changes/sec | Activity Level |
|---|---|---|
| s1 free roam | 122,000 | Idle free roam |
| s2 event prompt | 127,000 | UI active |
| s3 race start | 264,000 - 397,000 | Active racing (physics heavy) |
| s4 race finish | 131,000 | Pre-finish, stable |
| s5 post-vanessa | 130,000 | Post-progression |
| s10 post-race | 129,000 | Result screen |
| s12 garage | 120,000 | Menu idle |
| s13 collectible | 122,000 | Free roam |
| s14 tournament | 120,000 | Free roam |

## Cross-State Analysis

Diff two different states' baseline snapshots to find what changed due to game progression:

```python
import json, struct

def load(path):
    with open(path) as f: return json.load(f)

s1 = load('dumps/s1_free_roam/snap_000.json')
s2 = load('dumps/s2_event_prompt/snap_000.json')

for key in s1:
    if key not in s2: continue
    ha, hb = s1[key], s2[key]
    if ha == hb or not ha or not hb: continue
    ba, bb = bytes.fromhex(ha), bytes.fromhex(hb)
    start = int(key, 16)
    for off in range(0, len(ba), 4):
        va = struct.unpack_from('<I', ba, off)[0]
        vb = struct.unpack_from('<I', bb, off)[0]
        if va != vb and va < 200 and vb < 200:
            print(f'0x{start+off:08X}: {va} -> {vb}')
```

## Useful Comparisons

| Comparison | What It Finds |
|---|---|
| s1 vs s2 | Event prompt state |
| s1 vs s12 | Garage state |
| s1 vs s5 | Progression (post-Vanessa unlocks) |
| s1 vs s10 | Post-race state |
| s13 vs s14 | Tournament win + Lexus purchase |
| s3 diff_NNN_MMM | Race physics data |
| s1 diff_NNN_MMM | Idle animation data |

## Tools

| Tool | Purpose |
|---|---|
| `full_diff.py 1 10` | Capture 10 snapshots of state 1 |
| `full_diff.py --batch` | Capture all 9 states (5 snaps each) |
| `watch.py` | Live poll of money + position |
| `listen.py` | Event detection (race start/finish, money) |
