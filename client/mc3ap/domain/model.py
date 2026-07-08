"""Core domain model — immutable dataclasses for everything.

These types are the single source of truth.  Every layer
(APWorld, Python client, payload, tests) consumes these definitions.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import FrozenSet, Mapping, Optional, Sequence, Tuple

from .ids import (
    AbilityId,
    CityId,
    ClubId,
    CollectibleId,
    CollectibleTier,
    CosmeticId,
    EventId,
    GateId,
    GrantedVehicleInstance,
    ItemId,
    LocationId,
    PartCategoryId,
    PartId,
    RewardId,
    TournamentId,
    TrapId,
    VehicleCategory,
    VehicleClass,
    VehicleId,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Enumerations
# ═══════════════════════════════════════════════════════════════════════════════

class ItemClassification(enum.Enum):
    """Archipelago item classification."""
    PROGRESSION = "progression"
    USEFUL = "useful"
    FILLER = "filler"
    TRAP = "trap"


class CheckGranularity(enum.Enum):
    COMPLETION = "completion"
    PER_RACE = "per_race"
    BOTH = "both"


class VehicleItemMode(enum.Enum):
    PERMITS_ONLY = "permits_only"
    DIRECT_GRANTS = "direct_grants"
    PERMITS_PLUS_VOUCHERS = "permits_plus_vouchers"


class GateDecisionType(enum.Enum):
    ALLOW_ORIGINAL = "allow_original"
    BLOCK_RETURN_TO_MENU = "block_return_to_menu"
    BLOCK_SHOW_MESSAGE = "block_show_message"
    BLOCK_FORCE_GARAGE = "block_force_garage"
    BLOCK_FORCE_FALLBACK_VEHICLE = "block_force_fallback_vehicle"
    SUPPRESS_REWARD = "suppress_reward"
    REPAIR_AND_CONTINUE = "repair_and_continue"


# ═══════════════════════════════════════════════════════════════════════════════
#  Item definitions
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ItemDefinition:
    item_id: ItemId
    name: str                          # AP-facing display name
    classification: ItemClassification
    count: int = 1                     # how many in the pool
    progressive_tier: Optional[int] = None  # None = non-progressive


@dataclass(frozen=True)
class TrapDefinition:
    """A trap that applies a temporary negative effect."""
    trap_id: TrapId
    name: str
    description: str
    duration_seconds: Optional[int] = None  # None = until next race


# ═══════════════════════════════════════════════════════════════════════════════
#  Location definitions
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LocationDefinition:
    location_id: LocationId
    name: str
    region: str                        # AP region name
    classification: ItemClassification = ItemClassification.PROGRESSION
    is_meta_check: bool = False        # completion-level check, not individual
    required_event_id: Optional[EventId] = None
    required_collectible_id: Optional[CollectibleId] = None


# ═══════════════════════════════════════════════════════════════════════════════
#  Event / Tournament / Club definitions
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EventDefinition:
    event_id: EventId
    name: str
    city: CityId
    race_type: str                     # ordered, circuit, autocross, track, unordered
    class_requirement: Optional[VehicleClass] = None
    category_requirement: Optional[VehicleCategory] = None
    is_tournament_race: bool = False
    is_club_race: bool = False
    tournament_id: Optional[TournamentId] = None
    club_id: Optional[ClubId] = None


@dataclass(frozen=True)
class TournamentDefinition:
    tournament_id: TournamentId
    name: str
    city: CityId
    race_ids: Tuple[EventId, ...]


@dataclass(frozen=True)
class ClubDefinition:
    club_id: ClubId
    name: str
    city: CityId
    vehicle_category: Optional[VehicleCategory]
    race_ids: Tuple[EventId, ...]


# ═══════════════════════════════════════════════════════════════════════════════
#  Vehicle definitions
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class VehicleDefinition:
    vehicle_id: VehicleId
    name: str
    manufacturer: str
    vehicle_class: VehicleClass
    vehicle_category: VehicleCategory
    is_prize_car: bool = False
    is_purchasable: bool = True
    price: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
#  Part definitions
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PartDefinition:
    part_id: PartId
    name: str
    category: PartCategoryId
    tier: int                          # 0 = stock, 1-3 = upgrades
    compatible_vehicles: FrozenSet[VehicleId] = field(default_factory=frozenset)
    price: int = 0
    is_visual: bool = False
    classification: ItemClassification = ItemClassification.USEFUL


# ═══════════════════════════════════════════════════════════════════════════════
#  Collectible definitions
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CollectibleDefinition:
    collectible_id: CollectibleId
    name: str
    city: CityId
    index: int                         # order within city


# ═══════════════════════════════════════════════════════════════════════════════
#  Ability definitions
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AbilityDefinition:
    ability_id: AbilityId
    name: str


# ═══════════════════════════════════════════════════════════════════════════════
#  Geography
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CityDefinition:
    city_id: CityId
    name: str
    is_starting: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
#  Rewards
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RewardDefinition:
    reward_id: RewardId
    name: str
    ap_controlled: bool = True         # should AP suppress this?


# ═══════════════════════════════════════════════════════════════════════════════
#  Goals
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class GoalDefinition:
    name: str
    required_items: FrozenSet[str] = field(default_factory=frozenset)
    required_locations: FrozenSet[str] = field(default_factory=frozenset)
    item_name: str = ""                # sentinel item for AP completion check