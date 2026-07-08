"""Slot data and seed contract generation for MC3 APWorld.

Slot data is sent to the client as part of the connect response.
The seed contract is a JSON file written during generate_output().
"""

import hashlib
import json
import os
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from . import MC3World


def build_slot_data(world: "MC3World", catalog) -> Dict[str, Any]:
    """Build the slot_data dict sent to the client on connect.

    Per AP convention, this should be minimal — the full seed contract
    is delivered as a file.
    """
    return {
        "game": "Midnight Club 3: DUB Edition Remix",
        "expected_serial": "SLUS-21355",
        "expected_crc": 0x60A42FF5,
        "seed_name": world.multiworld.seed_name if hasattr(world.multiworld, 'seed_name') else "unknown",
        "slot": world.player,
        "slot_name": world.player_name,
        "catalog_hash": _compute_catalog_hash(world),
        "contract_filename": f"mc3_seed_{world.player}.json",
    }


def write_seed_contract_json(world: "MC3World", output_directory: str):
    """Write the full seed contract as a JSON file for the client."""
    contract = _build_seed_contract_dict(world)
    filename = f"mc3_seed_{world.player}.json"
    path = os.path.join(output_directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(contract, f, indent=2, sort_keys=True)


def _build_seed_contract_dict(world: "MC3World") -> Dict[str, Any]:
    """Serialize the seed contract to a JSON-safe dict."""
    # Collect all item definitions
    item_table = {}
    for name, item_id in world.item_name_to_id.items():
        item_table[str(item_id)] = {
            "item_id": item_id,
            "name": name,
            "classification": _classify_str(name),
            "count": 1,
        }

    # Collect all location definitions
    location_table = {}
    for region in world.multiworld.regions:
        if region.player != world.player:
            continue
        for loc in region.locations:
            location_table[str(loc.address)] = {
                "location_id": loc.address,
                "name": loc.name,
                "region": region.name,
            }

    return {
        "schema_version": 1,
        "game": "Midnight Club 3: DUB Edition Remix",
        "expected_serial": "SLUS-21355",
        "expected_crc": 0x60A42FF5,
        "seed_name": world.multiworld.seed_name if hasattr(world.multiworld, 'seed_name') else "unknown",
        "slot": world.player,
        "slot_name": world.player_name,
        "catalog_hash": _compute_catalog_hash(world),
        "item_table": item_table,
        "location_table": location_table,
        "event_table": {},
        "collectible_table": {},
        "vehicle_table": {},
        "part_table": {},
        "gate_table": {},
        "goal_definition": {
            "name": "Complete Career",
            "item_name": "Victory",
        },
        "options": _serialize_options(world),
    }


def _compute_catalog_hash(world: "MC3World") -> str:
    """Deterministic hash of the catalog used for this seed."""
    raw = json.dumps({
        "seed": world.multiworld.seed_name if hasattr(world.multiworld, 'seed_name') else "",
        "slot": world.player,
        "item_count": len(world.item_name_to_id),
    }, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _classify_str(name: str) -> str:
    n = name.lower()
    if "trap:" in n:
        return "trap"
    if "permit" in n or "license" in n or "grant" in n or "city" in n:
        return "progression"
    if "money pack" in n:
        return "useful"
    if "victory" in n:
        return "progression"
    return "filler"


def _serialize_options(world: "MC3World") -> Dict[str, Any]:
    """Serialize options to a JSON-safe dict."""
    return {
        "progression_mode": world.options.progression_mode.value,
        "vehicle_itemization": world.options.vehicle_itemization.value,
        "part_itemization": world.options.part_itemization.value,
        "collectible_checks": world.options.collectible_checks.value,
        "collectible_reward_randomization": world.options.collectible_reward_randomization.value,
        "cosmetic_checks": world.options.cosmetic_checks.value,
        "money_checks": world.options.money_checks.value,
        "tournament_granularity": world.options.tournament_granularity.value,
        "club_granularity": world.options.club_granularity.value,
        "vanilla_reward_policy": world.options.vanilla_reward_policy.value,
        "trap_percentage": world.options.trap_percentage.value,
        "garage_slot_logic": world.options.garage_slot_logic.value,
        "starting_city_policy": world.options.starting_city_policy.value,
        "starting_vehicle_policy": world.options.starting_vehicle_policy.value,
    }