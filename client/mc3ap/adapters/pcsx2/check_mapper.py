"""Map live game signals (mc3api GameWatcher events) to AP location IDs.

This is the bridge between reverse-engineered runtime state and the
Archipelago location space. It is deliberately a pure function over event
data so it can be unit-tested without an emulator or an AP server.

Signal sources (all confirmed — see docs/stats_catalog.md):
  * RouteCompleted(route_id, won)  -> "Race Win: <route>" when won
  * CollectiblePicked(city, total) -> "Collectible: <city> #<n>"
  * StatChanged(UOTk)              -> "Tournament Won #<n>"

Route ids are the stable IT:r indices the game assigns the first time a
route is completed. The route_id -> human name table is data-driven
(loaded from the world catalog); unknown ids still produce a stable,
deterministic location name so no check is ever silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


# Stable route-id -> event name. Seeded from discovered dumps; extend as the
# curated catalog grows. Ids are the IT:r catalog indices.
KNOWN_ROUTE_NAMES: Dict[int, str] = {
    0x01: "San Diego: Vanessa Race 1",
    0x04: "San Diego: Vanessa Race 2",
    0x0F: "San Diego: Ordered Race (0x0F)",
    0x16: "San Diego: Ordered Race (0x16)",
    0x3E: "San Diego Autocross: Ocean's Eleven Race 1",
    0x3F: "San Diego Autocross: Ocean's Eleven Race 2",
    0x41: "San Diego Autocross: Ocean's Eleven Race 3",
}


def route_location_name(route_id: int) -> str:
    known = KNOWN_ROUTE_NAMES.get(route_id)
    if known:
        return f"Race Win: {known}"
    return f"Race Win: Route 0x{route_id:X}"


def collectible_location_name(city: int, ordinal: int) -> str:
    city_name = {0: "San Diego", 1: "Atlanta", 2: "Detroit", 3: "Tokyo"}.get(city, f"City {city}")
    return f"Collectible: {city_name} #{ordinal}"


def tournament_location_name(ordinal: int) -> str:
    return f"Tournament Won #{ordinal}"


@dataclass(frozen=True)
class DetectedCheck:
    """A location check derived from a game event."""
    location_name: str
    source: str            # "route" | "collectible" | "tournament"
    raw_id: int            # route id / city id / tournament ordinal


def map_event_to_checks(event) -> List[DetectedCheck]:
    """Translate a single mc3api GameEvent into zero or more location checks.

    Imported lazily so this module has no hard dependency on mc3api at import
    time (keeps the domain/client importable without the API installed).
    """
    from mc3api.events import CollectiblePicked, RouteCompleted, StatChanged
    from mc3api.stats import TAGS

    checks: List[DetectedCheck] = []

    if isinstance(event, RouteCompleted):
        if event.won:
            checks.append(DetectedCheck(
                route_location_name(event.route_id), "route", event.route_id))
    elif isinstance(event, CollectiblePicked):
        checks.append(DetectedCheck(
            collectible_location_name(event.city, event.city_count),
            "collectible", event.city))
    elif isinstance(event, StatChanged) and event.tag == TAGS.TOURNAMENT_WINS:
        checks.append(DetectedCheck(
            tournament_location_name(event.new), "tournament", event.new))

    return checks


class CheckResolver:
    """Maps DetectedChecks to AP LocationIds via a name->id table.

    The table normally comes from the seed contract / world datapackage
    (location_name_to_id). Unknown names are reported so the caller can log
    dropped checks instead of silently losing them.
    """

    def __init__(self, name_to_id: Dict[str, int]):
        self._name_to_id = dict(name_to_id)
        self.unresolved: List[str] = []

    def resolve(self, check: DetectedCheck) -> Optional[int]:
        loc_id = self._name_to_id.get(check.location_name)
        if loc_id is None:
            self.unresolved.append(check.location_name)
        return loc_id

    def resolve_all(self, checks: List[DetectedCheck]) -> List[int]:
        out = []
        for c in checks:
            loc_id = self.resolve(c)
            if loc_id is not None:
                out.append(loc_id)
        return out
