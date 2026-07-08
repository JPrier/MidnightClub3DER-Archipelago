"""mc3api — Modding API for Midnight Club 3: DUB Edition Remix (PS2, SLUS-21355).

Connects to a running stock PCSX2 instance and exposes typed, validated access
to game state: money, career stats, collectibles, race results, vehicles,
profile data, and low-level memory / hook primitives.

Quick start:
    from mc3api import MC3Game

    game = MC3Game.connect()
    print(game.money)                    # wallet cash
    print(game.stats.tournament_wins)    # career stat (tag scan)
    print(game.vehicles())               # vehicle catalog

    for event in game.watch():           # poll-based game event stream
        print(event)

Design notes:
- All game-state parsing is implemented as pure functions over bytes
  (see stats.py, vehicles.py) so it is unit-testable without an emulator.
- The stats catalog MUST be accessed by tag scan, never fixed address —
  entries insert-shift as new stat types first occur. See docs/stats_catalog.md.
"""

from .bridge import PCSX2Bridge, BridgeError
from .memmap import MemoryMap
from .stats import StatsCatalog, StatEntry, TAGS
from .vehicles import Vehicle, parse_vehicle_array
from .game import MC3Game
from .events import GameWatcher, GameEvent, MoneyChanged, CollectiblePicked, RouteCompleted, StatChanged

__version__ = "0.1.0"

__all__ = [
    "MC3Game",
    "PCSX2Bridge",
    "BridgeError",
    "MemoryMap",
    "StatsCatalog",
    "StatEntry",
    "TAGS",
    "Vehicle",
    "parse_vehicle_array",
    "GameWatcher",
    "GameEvent",
    "MoneyChanged",
    "CollectiblePicked",
    "RouteCompleted",
    "StatChanged",
]
