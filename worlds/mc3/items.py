"""APWorld item definitions for MC3.

ITEM_NAME_TO_ID is the canonical numeric-ID mapping required by Archipelago.
IDs start at 7160000 (avoiding collisions with other AP games per convention).
ITEM_TABLE provides ItemDefinition-like metadata for each item.
filler_item_names is used by get_filler_item_name().
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from BaseClasses import Item, ItemClassification

# ── Base ID range ────────────────────────────────────────────────────────────
MC3_ITEM_BASE = 7160000

_item_counter = MC3_ITEM_BASE


def _next() -> int:
    global _item_counter
    _item_counter += 1
    return _item_counter - 1


# ── Item metadata ────────────────────────────────────────────────────────────

@dataclass
class ItemDefinition:
    ap_id: int
    name: str
    classification: ItemClassification


# ── Item name → ID mapping ───────────────────────────────────────────────────

ITEM_NAME_TO_ID: Dict[str, int] = {
    "Victory":                          _next(),
    "City Permit: San Diego":           _next(),
    "City Permit: Atlanta":             _next(),
    "City Permit: Detroit":             _next(),
    "City Permit: Tokyo":               _next(),
    "Vehicle Class License: D":         _next(),
    "Vehicle Class License: C":         _next(),
    "Vehicle Class License: B":         _next(),
    "Vehicle Class License: A":         _next(),
    "Ability Permit: Zone":             _next(),
    "Ability Permit: Agro":             _next(),
    "Ability Permit: Roar":             _next(),
    "Progressive Garage Slot":          _next(),
}

# Reverse mapping
ID_TO_ITEM_NAME: Dict[int, str] = {v: k for k, v in ITEM_NAME_TO_ID.items()}

# Item definitions for use by create_item()
ITEM_TABLE: Dict[str, ItemDefinition] = {
    name: ItemDefinition(ap_id=item_id, name=name, classification=_guess_classification(name))
    for name, item_id in ITEM_NAME_TO_ID.items()
}

# Filler items that are safe to repeat
filler_item_names: List[str] = [
    "Money Pack: $500",
    "Money Pack: $1,000",
]


def create_mc3_item(world: "MC3World", name: str) -> Item:
    """Create a standard MC3 Archipelago item."""
    item_id = ITEM_NAME_TO_ID.get(name)
    if item_id is None:
        item_id = _next()
        ITEM_NAME_TO_ID[name] = item_id
        ID_TO_ITEM_NAME[item_id] = name

    classification = _guess_classification(name)
    return Item(name, classification, item_id, world.player)


def build_item_pool(world: "MC3World", catalog) -> list:
    """Build the full item pool from the game catalog and options."""
    pool: list = []

    # Sentinel goal item
    pool.append(create_mc3_item(world, "Victory"))

    # Cities (skip starting city per options)
    for city in catalog.cities.values():
        if city.is_starting and world.options.starting_city_policy.value == 0:
            continue
        pool.append(create_mc3_item(world, f"City Permit: {city.name}"))

    # Vehicle classes
    for vc in ("D", "C", "B", "A"):
        if vc == "D" and world.options.progression_mode.value == 0:
            continue  # D is free in career mode
        pool.append(create_mc3_item(world, f"Vehicle Class License: {vc}"))

    # Vehicle category permits
    for cat in ("Tuner", "Muscle", "Luxury", "SUV", "Exotic", "SportBike", "Chopper"):
        pool.append(create_mc3_item(world, f"Vehicle Category Permit: {cat}"))

    # Individual vehicle items (mode-dependent)
    for vehicle in catalog.vehicles.values():
        mode = world.options.vehicle_itemization
        if mode.value == 0:  # permits_only
            pool.append(create_mc3_item(world, f"Vehicle Permit: {vehicle.name}"))
        elif mode.value == 1:  # direct_grants
            pool.append(create_mc3_item(world, f"Vehicle Grant: {vehicle.name}"))
        elif mode.value == 2:  # permits_plus_vouchers
            pool.append(create_mc3_item(world, f"Vehicle Permit: {vehicle.name}"))
            pool.append(create_mc3_item(world, f"Vehicle Voucher: {vehicle.name}"))

    # Abilities
    pool.append(create_mc3_item(world, "Ability Permit: Zone"))
    pool.append(create_mc3_item(world, "Ability Permit: Agro"))
    pool.append(create_mc3_item(world, "Ability Permit: Roar"))

    # Progressive garage slots
    for _ in range(5):
        pool.append(create_mc3_item(world, "Progressive Garage Slot"))

    # Parts (populated after catalog extraction)
    if catalog.parts:
        for part in catalog.parts.values():
            mode = world.options.part_itemization
            if mode.value == 0:  # tiers
                pool.append(create_mc3_item(world, f"Progressive Performance Tier"))
            elif mode.value == 1:  # categories
                pool.append(create_mc3_item(world, f"Part Category Permit: {part.category}"))
            elif mode.value == 2:  # individual
                pool.append(create_mc3_item(world, f"Part Permit: {part.part_id}"))

    # Money packs as filler
    money_packs = [("$500", 500), ("$1,000", 1000), ("$5,000", 5000)]
    for label, _ in money_packs:
        pool.append(create_mc3_item(world, f"Money Pack: {label}"))

    # Collectible rewards
    pool.append(create_mc3_item(world, "Rockstar Logo Reward: Flags"))
    pool.append(create_mc3_item(world, "Rockstar Logo Reward: Rockstar Plates"))
    pool.append(create_mc3_item(world, "Rockstar Logo Reward: Race Starter Riders"))

    # Traps (percentage-based)
    trap_count = int(len(pool) * world.options.trap_percentage.value / 100)
    for i in range(trap_count):
        pool.append(create_mc3_item(world, f"Trap: Forced Rental Car"))

    return pool


def _guess_classification(name: str) -> ItemClassification:
    """Classify an item as progression, useful, filler, or trap."""
    n = name.lower()
    if "trap:" in n:
        return ItemClassification.trap
    if "permit" in n or "license" in n or "grant" in n or "city" in n:
        return ItemClassification.progression
    if "money pack" in n:
        return ItemClassification.useful
    if "logo reward" in n:
        return ItemClassification.useful
    if "victory" in n:
        return ItemClassification.progression
    return ItemClassification.filler