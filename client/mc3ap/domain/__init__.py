"""MC3AP domain — pure, framework-free core logic.

All domain types, the reducer, invariants, gate evaluation,
and semantic classifiers live here.  Nothing in this package
knows about WebSockets, process memory, or Archipelago internals.
"""

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
    HookId,
    ItemId,
    LocationId,
    PartCategoryId,
    PartId,
    RewardId,
    TournamentId,
    TrapId,
    VanillaFlagId,
    VehicleCategory,
    VehicleClass,
    VehicleId,
)
from .model import (
    AbilityDefinition,
    CheckGranularity,
    CityDefinition,
    ClubDefinition,
    CollectibleDefinition,
    EventDefinition,
    GateDecisionType,
    GoalDefinition,
    ItemClassification,
    ItemDefinition,
    LocationDefinition,
    PartDefinition,
    RewardDefinition,
    TournamentDefinition,
    TrapDefinition,
    VehicleDefinition,
    VehicleItemMode,
)
from .catalog import GameCatalog, make_starter_catalog
from .seed_contract import (
    GateDefinition,
    GateDecision,
    MC3Options,
    SeedContract,
)
from .reducer import (
    ClientState,
    DesiredGameState,
    TrapEvent,
    apply_full_inventory_reset,
    apply_location_checked,
    apply_received_item,
    reduce_desired_state,
)
from .gates import evaluate_gate
from .item_semantics import ItemSemantic, ItemSemanticInfo, classify_item_name
from .check_semantics import CheckSemantic, CheckSemanticInfo, classify_check_name

__all__ = [
    # IDs
    "AbilityId", "CityId", "ClubId", "CollectibleId", "CollectibleTier",
    "CosmeticId", "EventId", "GateId", "GrantedVehicleInstance", "HookId",
    "ItemId", "LocationId", "PartCategoryId", "PartId", "RewardId",
    "TournamentId", "TrapId", "VanillaFlagId", "VehicleCategory",
    "VehicleClass", "VehicleId",
    # Model
    "AbilityDefinition", "CheckGranularity", "CityDefinition", "ClubDefinition",
    "CollectibleDefinition", "EventDefinition", "GateDecisionType",
    "GoalDefinition", "ItemClassification", "ItemDefinition",
    "LocationDefinition", "PartDefinition", "RewardDefinition",
    "TournamentDefinition", "TrapDefinition", "VehicleDefinition",
    "VehicleItemMode",
    # Catalog
    "GameCatalog", "make_starter_catalog",
    # Contracts
    "GateDefinition", "GateDecision", "MC3Options", "SeedContract",
    # Reducer
    "ClientState", "DesiredGameState", "TrapEvent",
    "apply_full_inventory_reset", "apply_location_checked",
    "apply_received_item", "reduce_desired_state",
    # Gates
    "evaluate_gate",
    # Semantics
    "ItemSemantic", "ItemSemanticInfo", "classify_item_name",
    "CheckSemantic", "CheckSemanticInfo", "classify_check_name",
]