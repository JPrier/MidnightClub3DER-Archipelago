"""CLI status dump: python -m mc3api"""

import sys

from .game import MC3Game
from .stats import TAGS


def main() -> int:
    print("mc3api — connecting to PCSX2...")
    try:
        game = MC3Game.connect(timeout=10)
    except Exception as e:
        print(f"[FAIL] {e}")
        return 1

    with game:
        print(f"Connected: {game}")
        print(f"\nMoney:            ${game.money:,}")
        print(f"Race position:    {game.live_race_position}")
        print(f"Last event:       {game.last_event_path or '(none)'}")

        s = game.stats
        print(f"\nCareer stats ({len(s)} catalog entries):")
        print(f"  Wins:             {s.race_wins}")
        print(f"  Races entered:    {s.races_entered}")
        print(f"  Tournament wins:  {s.tournament_wins}")
        print(f"  Collectibles:     {s.collectibles_total} "
              f"(per city: {[s.collectibles_in_city(c) for c in range(3)]})")
        print(f"  Career earnings:  ${s.career_earnings:,}")
        print(f"  Completed routes: {[hex(r) for r in s.completed_route_ids]}")

        vehicles = game.vehicles()
        print(f"\nVehicles loaded: {len(vehicles)}")
        for v in vehicles[:5]:
            print(f"  [{v.index:3d}] {v.name}")
        if len(vehicles) > 5:
            print(f"  ... and {len(vehicles) - 5} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
