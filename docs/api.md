# mc3api — Modding API Reference

Python API for reading and manipulating a running Midnight Club 3: DUB Edition
Remix game (SLUS-21355) inside **stock PCSX2**. This is the public layer other
mods (including the Archipelago client) build on.

## Requirements

- Windows, Python 3.10+
- Stock PCSX2 (v2.x) with cheats enabled
- `60A42FF5.pnach` payload installed in `cheats/` (provides the MC3AP mailbox
  marker used to locate EE RAM — see `tools/build_payload.py`)

## Quick start

```python
from mc3api import MC3Game

game = MC3Game.connect()          # finds PCSX2, locates EE RAM via mailbox

# Wallet
print(game.money)                 # -> 13900
game.money += 5000                # write is instant, game UI updates

# Career stats (tag-scanned catalog — robust against entry insertion)
s = game.stats.refresh()
s.race_wins                       # 6
s.tournament_wins                 # 1
s.collectibles_total              # 1
s.collectibles_in_city(0)         # 1  (0=San Diego)
s.completed_route_ids             # [1, 4, 15, 22, 62, 63, 65]
s.route_best_time(62)             # 61.011 (seconds)

# Event identity
game.last_event_path              # 'autox\\med\\sd_autox_med_oceanseleven_race01'

# Vehicles
for v in game.vehicles():         # Vehicle(index, ee_addr, name_ptr, name)
    print(v.name)

# Race state
game.live_race_position           # 1..6 while racing

# Low-level escape hatch
game.read_u32(0x00800870)
game.write(0x00720010, b"\x2a\x00\x00\x00")
game.hexdump(0x007D2310, 128)
```

## Event stream (poll-based check detection)

No game hooks are needed to *detect* progress — the stats catalog changes
deterministically on every check-worthy action:

```python
for event in game.watch(interval=1.0):
    match event:
        case CollectiblePicked(city=c, total=t):   ...  # Rockstar logo
        case RouteCompleted(route_id=r, won=w):    ...  # race finished
        case MoneyChanged(delta=d):                ...
        case StatChanged(tag="UOTk", new=n):       ...  # tournament win
```

`GameWatcher.poll_once()` returns the events since the previous poll — use it
if you drive your own loop.

## Modules

| Module | Purpose |
|---|---|
| `mc3api.game` | `MC3Game` facade — connect, wallet, profile, vehicles, watch |
| `mc3api.stats` | `StatsCatalog` tag-scan parser + `TAGS` constants |
| `mc3api.events` | `GameWatcher` + typed `GameEvent`s |
| `mc3api.bridge` | `PCSX2Bridge` process-memory bridge (EE-space addressing) |
| `mc3api.memmap` | `MemoryMap` — all confirmed EE addresses |
| `mc3api.vehicles` | vehicle array parser |
| `mc3api.hooks` | `HookManager` — patch/restore verified JAL call sites |

## CLI

```bash
python -m mc3api        # connection + game state status dump
```

## Rules for extending

1. **Never** hardcode an address inside the stats catalog — entries insert-shift.
   Add a tag to `TAGS` and use the scan.
2. New memory fields go into `memmap.py` only with differential proof
   (documented in `targets.yaml` + `docs/`).
3. Parsing logic must be a pure function over `bytes` so it stays unit-testable
   without an emulator (see `stats.parse_catalog`, `vehicles.parse_vehicle_array`).
4. Only JAL call sites may be live-patched (`HookManager` enforces this).

## Testing

```bash
python -m pytest tests/unit       # no emulator needed
python -m pytest tests/emulator   # auto-skips unless PCSX2 + game + pnach live
```
