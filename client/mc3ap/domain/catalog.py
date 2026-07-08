"""Canonical static catalog of MC3 content.

Populated by combining:
  1. extracted ASSETS.DAT / vehicle.lst metadata
  2. runtime probes from the EE payload
  3. manually-curated metadata
  4. public-guide validation
  5. checksum / hash validation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Mapping

from .ids import (
    AbilityId,
    CityId,
    ClubId,
    CollectibleId,
    EventId,
    PartId,
    RewardId,
    TournamentId,
    VehicleId,
)
from .model import (
    AbilityDefinition,
    CityDefinition,
    ClubDefinition,
    CollectibleDefinition,
    EventDefinition,
    PartDefinition,
    RewardDefinition,
    TournamentDefinition,
    VehicleDefinition,
)


@dataclass(frozen=True)
class GameCatalog:
    schema_version: int = 1
    game: str = "Midnight Club 3: DUB Edition Remix"
    target_serial: str = "SLUS-21355"
    target_crc: int = 0x60A42FF5

    vehicles: Mapping[VehicleId, VehicleDefinition] = field(default_factory=dict)
    parts: Mapping[PartId, PartDefinition] = field(default_factory=dict)
    events: Mapping[EventId, EventDefinition] = field(default_factory=dict)
    tournaments: Mapping[TournamentId, TournamentDefinition] = field(default_factory=dict)
    clubs: Mapping[ClubId, ClubDefinition] = field(default_factory=dict)
    cities: Mapping[CityId, CityDefinition] = field(default_factory=dict)
    collectibles: Mapping[CollectibleId, CollectibleDefinition] = field(default_factory=dict)
    abilities: Mapping[AbilityId, AbilityDefinition] = field(default_factory=dict)
    reward_rules: Mapping[RewardId, RewardDefinition] = field(default_factory=dict)

    # ── derived indexes (built by factory) ──────────────────────────────────

    events_by_city: Mapping[CityId, FrozenSet[EventId]] = field(default_factory=dict)
    vehicles_by_class: Mapping[str, FrozenSet[VehicleId]] = field(default_factory=dict)
    vehicles_by_category: Mapping[str, FrozenSet[VehicleId]] = field(default_factory=dict)
    parts_by_category: Mapping[str, FrozenSet[PartId]] = field(default_factory=dict)

    def event_ids(self) -> FrozenSet[EventId]:
        return frozenset(self.events.keys())

    def vehicle_ids(self) -> FrozenSet[VehicleId]:
        return frozenset(self.vehicles.keys())

    def part_ids(self) -> FrozenSet[PartId]:
        return frozenset(self.parts.keys())


# ── Minimal curated starter catalog ───────────────────────────────────────────
# These are *placeholders* — every entry must be validated against runtime probes
# before being considered authoritative.

_STARTER_CITIES: Mapping[CityId, CityDefinition] = {
    CityId("san_diego"): CityDefinition(city_id=CityId("san_diego"), name="San Diego", is_starting=True),
    CityId("atlanta"):   CityDefinition(city_id=CityId("atlanta"), name="Atlanta"),
    CityId("detroit"):   CityDefinition(city_id=CityId("detroit"), name="Detroit"),
    CityId("tokyo"):     CityDefinition(city_id=CityId("tokyo"), name="Tokyo"),
}

_STARTER_ABILITIES: Mapping[AbilityId, AbilityDefinition] = {
    AbilityId("zone"): AbilityDefinition(ability_id=AbilityId("zone"), name="Zone"),
    AbilityId("agro"): AbilityDefinition(ability_id=AbilityId("agro"), name="Agro"),
    AbilityId("roar"): AbilityDefinition(ability_id=AbilityId("roar"), name="Roar"),
}

_VEHICLE_CATEGORIES = ("tuner", "muscle", "luxury", "suv", "exotic", "sport_bike", "chopper")
_VEHICLE_CLASSES = ("D", "C", "B", "A")


def make_starter_catalog() -> GameCatalog:
    """Return a minimal catalog with only verified static facts.

    Everything here has been confirmed via public sources (game guides,
    cheat-code references, MC3CarRandomizer code).  No runtime-probe-only
    data is included yet.
    """
    return GameCatalog(
        cities=_STARTER_CITIES,
        abilities=_STARTER_ABILITIES,
        # vehicles, events, parts, collectibles — populated after RE phase
    )