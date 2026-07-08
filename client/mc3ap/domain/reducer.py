"""Pure reducer: AP item log + check set + seed contract → DesiredGameState.

This is the heart of the domain.  It is:
  • deterministic — same inputs always produce the same output
  • idempotent   — replaying the same item log does not double-unlock
  • monotonic    — receiving items never removes unlocks (except traps)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import FrozenSet, Mapping, Optional, Sequence, Tuple

from .ids import (
    AbilityId,
    CityId,
    CollectibleId,
    CollectibleTier,
    CosmeticId,
    EventId,
    GrantedVehicleInstance,
    ItemId,
    LocationId,
    PartCategoryId,
    PartId,
    VehicleCategory,
    VehicleClass,
    VehicleId,
)
from .model import (
    GoalDefinition,
    ItemClassification,
    ItemDefinition,
    TrapDefinition,
)
from .seed_contract import GateDefinition, GateDecision, MC3Options, SeedContract


# ═══════════════════════════════════════════════════════════════════════════════
#  State snapshots
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TrapEvent:
    trap_id: str
    applied: bool = False


@dataclass(frozen=True)
class ClientState:
    """Persisted state: everything the client remembers across restarts."""
    received_items: Mapping[int, ItemId] = field(default_factory=dict)  # ap_index → item_id
    item_instance_ids: Mapping[ItemId, FrozenSet[int]] = field(default_factory=dict)  # item_id → ap_index set
    checked_locations: FrozenSet[LocationId] = field(default_factory=frozenset)
    goal_sent_to_ap: bool = False
    total_ap_money_applied: int = 0


@dataclass(frozen=True)
class DesiredGameState:
    """What the game runtime *should* look like right now."""
    schema_version: int = 1
    sequence: int = 0
    state_hash: str = ""

    seed_hash: str = ""
    slot: int = 1
    profile_hash: int = 0

    checked_locations: FrozenSet[LocationId] = field(default_factory=frozenset)

    # ── unlocked by AP items ────────────────────────────────────────────────
    allowed_cities: FrozenSet[CityId] = field(default_factory=frozenset)
    allowed_events: FrozenSet[EventId] = field(default_factory=frozenset)
    allowed_vehicle_classes: FrozenSet[VehicleClass] = field(default_factory=frozenset)
    allowed_vehicle_categories: FrozenSet[VehicleCategory] = field(default_factory=frozenset)
    allowed_vehicles: FrozenSet[VehicleId] = field(default_factory=frozenset)
    granted_vehicles: FrozenSet[GrantedVehicleInstance] = field(default_factory=frozenset)
    allowed_parts: FrozenSet[PartId] = field(default_factory=frozenset)
    allowed_part_categories: FrozenSet[PartCategoryId] = field(default_factory=frozenset)
    allowed_abilities: FrozenSet[AbilityId] = field(default_factory=frozenset)
    allowed_cosmetics: FrozenSet[CosmeticId] = field(default_factory=frozenset)

    total_ap_money: int = 0
    garage_slot_limit: int = 30
    collectible_reward_tiers: FrozenSet[CollectibleTier] = field(default_factory=frozenset)

    pending_traps: Tuple[TrapEvent, ...] = ()
    goal_completed: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
#  Reducer
# ═══════════════════════════════════════════════════════════════════════════════

def _hash_state(state: DesiredGameState) -> str:
    """Stable hash of all semantically meaningful fields."""
    blob = json.dumps({
        "allowed_cities": sorted(state.allowed_cities),
        "allowed_events": sorted(state.allowed_events),
        "allowed_vehicles": sorted(state.allowed_vehicles),
        "granted_vehicles": sorted(state.granted_vehicles),
        "allowed_parts": sorted(state.allowed_parts),
        "allowed_abilities": sorted(state.allowed_abilities),
        "total_ap_money": state.total_ap_money,
        "garage_slot_limit": state.garage_slot_limit,
        "checked_locations": sorted(state.checked_locations),
    }, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def reduce_desired_state(
    seed: SeedContract,
    client_state: ClientState,
    sequence: int = 0,
) -> DesiredGameState:
    """Pure function: compute the world the game should reflect.

    Receiving more items is monotonic — locks only open, never close
    (except for trap effects, which are transient).
    """

    # ── build the set of items we own by name ───────────────────────────────
    owned_item_names: set[str] = set()
    item_counts: dict[str, int] = {}

    for item_id, ap_indices in client_state.item_instance_ids.items():
        definition = seed.item_table.get(item_id)
        if definition is None:
            continue
        count = len(ap_indices)
        item_counts[definition.name] = count
        owned_item_names.add(definition.name)

    # ── evaluate every gate ─────────────────────────────────────────────────
    def _gate_passed(gate: GateDefinition) -> bool:
        # all required_items must be owned
        for name in gate.required_items:
            if name not in owned_item_names:
                return False
        # at least one required_any set must be fully satisfied
        if gate.required_any:
            if not any(
                all(name in owned_item_names for name in group)
                for group in gate.required_any
            ):
                return False
        # required_counts
        for name, needed in gate.required_counts.items():
            if item_counts.get(name, 0) < needed:
                return False
        # required_locations (all must be checked)
        for loc_name in gate.required_locations:
            # look up location ID by name; if not checked, fail
            loc_id = _loc_id_from_name(seed, loc_name)
            if loc_id is None or loc_id not in client_state.checked_locations:
                return False
        return True

    # ── compute derived unlock sets ─────────────────────────────────────────

    allowed_cities: set[CityId] = set()
    allowed_events: set[EventId] = set()
    allowed_vehicle_classes: set[VehicleClass] = set()
    allowed_vehicle_categories: set[VehicleCategory] = set()
    allowed_vehicles: set[VehicleId] = set()
    granted_vehicles: set[GrantedVehicleInstance] = set()
    allowed_parts: set[PartId] = set()
    allowed_part_categories: set[PartCategoryId] = set()
    allowed_abilities: set[AbilityId] = set()
    allowed_cosmetics: set[CosmeticId] = set()
    collectible_tiers: set[CollectibleTier] = set()
    total_money: int = 0

    # Collectibles: tier rewards based on checked logo locations
    logo_count = sum(
        1 for loc_id in client_state.checked_locations
        if loc_id in seed.location_table
        and "logo_collected" in seed.location_table[loc_id].name.lower()
    )
    for tier_def in (("12_logos", 12), ("24_logos", 24), ("36_logos", 36)):
        tier_name, threshold = tier_def
        if logo_count >= threshold:
            tier = CollectibleTier(tier_name)
            # Only grant if AP says it's allowed (tier is in item table as progression)
            if tier_name in owned_item_names or not seed.options.collectible_reward_randomization:
                collectible_tiers.add(tier)

    # Money — total from all money-pack items received
    _MONEY_PATTERNS = {
        "Money Pack: $500": 500,
        "Money Pack: $1,000": 1000,
        "Money Pack: $5,000": 5000,
        "Money Pack: $10,000": 10000,
        "Money Pack: $50,000": 50000,
    }
    for name, count in item_counts.items():
        if name in _MONEY_PATTERNS:
            total_money += _MONEY_PATTERNS[name] * count

    # Garage slots
    _SLOT_ITEM = "Progressive Garage Slot"
    base_slots = 30
    extra_slots = item_counts.get(_SLOT_ITEM, 0)
    garage_slots = min(base_slots + extra_slots, 60)  # cap at 60

    # Goal detection
    goal_complete = False
    if seed.goal_definition.item_name and seed.goal_definition.item_name in owned_item_names:
        goal_complete = True
    elif seed.goal_definition.required_locations:
        goal_complete = all(
            _loc_id_from_name(seed, name) in client_state.checked_locations
            for name in seed.goal_definition.required_locations
            if _loc_id_from_name(seed, name) is not None
        )

    # Evaluate every gate → unlock accordingly
    for gate in seed.gate_table.values():
        if not _gate_passed(gate):
            continue

        desc = gate.description.lower()

        if "city permit:" in desc:
            city = CityId(desc.split("city permit:")[-1].strip().replace(" ", "_").lower())
            allowed_cities.add(city)

        elif "event permit:" in desc:
            event = EventId(desc.split("event permit:")[-1].strip())
            allowed_events.add(event)

        elif "vehicle class license:" in desc:
            vc = VehicleClass(desc.split("vehicle class license:")[-1].strip().upper())
            allowed_vehicle_classes.add(vc)

        elif "vehicle category permit:" in desc:
            vc = VehicleCategory(desc.split("vehicle category permit:")[-1].strip().lower())
            allowed_vehicle_categories.add(vc)

        elif "vehicle permit:" in desc:
            vid = VehicleId(desc.split("vehicle permit:")[-1].strip().lower().replace(" ", "_"))
            allowed_vehicles.add(vid)

        elif "ability permit:" in desc:
            aid = AbilityId(desc.split("ability permit:")[-1].strip().lower())
            allowed_abilities.add(aid)

        elif "part category permit:" in desc:
            pc = PartCategoryId(desc.split("part category permit:")[-1].strip().lower())
            allowed_part_categories.add(pc)

        elif "part permit:" in desc:
            pid = PartId(desc.split("part permit:")[-1].strip())
            allowed_parts.add(pid)

    # Vehicle grants — each AP item instance = one GrantedVehicleInstance
    for item_id, ap_indices in client_state.item_instance_ids.items():
        definition = seed.item_table.get(item_id)
        if definition is None:
            continue
        if "Vehicle Grant:" in definition.name:
            vehicle_name = definition.name.split("Vehicle Grant:")[-1].strip().lower().replace(" ", "_")
            for idx in ap_indices:
                granted_vehicles.add(GrantedVehicleInstance(f"{vehicle_name}#{idx}"))

    # Build state
    state = DesiredGameState(
        sequence=sequence,
        seed_hash=seed.catalog_hash,
        slot=seed.slot,
        checked_locations=client_state.checked_locations,
        allowed_cities=frozenset(allowed_cities),
        allowed_events=frozenset(allowed_events),
        allowed_vehicle_classes=frozenset(allowed_vehicle_classes),
        allowed_vehicle_categories=frozenset(allowed_vehicle_categories),
        allowed_vehicles=frozenset(allowed_vehicles),
        granted_vehicles=frozenset(granted_vehicles),
        allowed_parts=frozenset(allowed_parts),
        allowed_part_categories=frozenset(allowed_part_categories),
        allowed_abilities=frozenset(allowed_abilities),
        allowed_cosmetics=frozenset(allowed_cosmetics),
        total_ap_money=total_money,
        garage_slot_limit=garage_slots,
        collectible_reward_tiers=frozenset(collectible_tiers),
        goal_completed=goal_complete,
    )

    # attach deterministic hash
    state = DesiredGameState(
        **{**state.__dict__, "state_hash": _hash_state(state)}
    )
    return state


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _loc_id_from_name(seed: SeedContract, name: str) -> Optional[LocationId]:
    """Reverse-lookup a location ID from its AP name."""
    for lid, defn in seed.location_table.items():
        if defn.name == name:
            return lid
    return None


def apply_received_item(
    client_state: ClientState,
    ap_index: int,
    item_id: ItemId,
) -> ClientState:
    """Return new ClientState with one additional received item."""
    new_items = dict(client_state.received_items)
    new_items[ap_index] = item_id

    new_instances = {k: set(v) for k, v in client_state.item_instance_ids.items()}
    new_instances.setdefault(item_id, set()).add(ap_index)
    new_instances[item_id] = frozenset(new_instances[item_id])

    return ClientState(
        received_items=new_items,
        item_instance_ids={k: frozenset(v) for k, v in new_instances.items()},
        checked_locations=client_state.checked_locations,
        goal_sent_to_ap=client_state.goal_sent_to_ap,
        total_ap_money_applied=client_state.total_ap_money_applied,
    )


def apply_location_checked(
    client_state: ClientState,
    location_id: LocationId,
) -> ClientState:
    """Return new ClientState with one additional checked location."""
    return ClientState(
        received_items=client_state.received_items,
        item_instance_ids=client_state.item_instance_ids,
        checked_locations=client_state.checked_locations | {location_id},
        goal_sent_to_ap=client_state.goal_sent_to_ap,
        total_ap_money_applied=client_state.total_ap_money_applied,
    )


def apply_full_inventory_reset(
    received_items: Mapping[int, ItemId],
) -> ClientState:
    """Build ClientState from a full AP inventory dump (index==0)."""
    new_instances: dict[ItemId, set[int]] = {}
    for idx, item_id in received_items.items():
        new_instances.setdefault(item_id, set()).add(idx)
    return ClientState(
        received_items=dict(received_items),
        item_instance_ids={k: frozenset(v) for k, v in new_instances.items()},
    )