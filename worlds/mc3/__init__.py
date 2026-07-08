"""Midnight Club 3: DUB Edition Remix — Archipelago World.

Compliant with Sections 21.5-21.12 of the design doc (upstream compliance).
"""

from typing import Any, Dict, List

from BaseClasses import Item, ItemClassification, Location, Region, Tutorial
from worlds.AutoWorld import WebWorld, World

from .items import ITEM_NAME_TO_ID, ITEM_TABLE, filler_item_names, create_mc3_item, build_item_pool
from .locations import LOCATION_NAME_TO_ID, create_regions_from_catalog, MC3Location
from .options import MC3Options
from .rules import apply_rules_from_gate_contract
from .catalog import load_catalog
from .slot_data import build_slot_data, write_seed_contract_json


class MC3Item(Item):
    game = "Midnight Club 3: DUB Edition Remix"


class MC3WebWorld(WebWorld):
    theme = "ocean"
    rich_text_options_doc = True
    tutorials = [
        Tutorial(
            "Multiworld Setup Guide",
            "A guide to setting up Midnight Club 3: DUB Edition Remix for Archipelago.",
            "English",
            "setup_en.md",
            "setup/en",
            ["Joshua Prier"],
        )
    ]
    bug_report_page = "https://github.com/JPrier/MidnightClub3DER-Archipelago/issues"


class MC3World(World):
    """Drive through MC3 Remix while Archipelago controls career progression,
    vehicles, upgrades, and collectibles."""

    game = "Midnight Club 3: DUB Edition Remix"
    web = MC3WebWorld()
    options_dataclass = MC3Options
    options: MC3Options
    topology_present = True

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID

    item_name_groups = {
        "Vehicles": set(),
        "Performance Parts": set(),
        "Visual Parts": set(),
        "Collectibles": set(),
        "Progression": set(),
        "Money": set(),
        "Traps": set(),
    }
    location_name_groups = {
        "Races": set(),
        "Tournaments": set(),
        "Club Races": set(),
        "Collectibles": set(),
        "Garages": set(),
        "Dealerships": set(),
    }

    def generate_early(self):
        self.catalog = load_catalog(self.options.catalog_mode)

    def create_item(self, name: str) -> MC3Item:
        definition = ITEM_TABLE.get(name)
        if definition:
            return MC3Item(name, definition.classification, definition.ap_id, self.player)
        # Fallback for dynamic items
        item_id = ITEM_NAME_TO_ID.get(name)
        if item_id is None:
            item_id = self._next_item_id()
            ITEM_NAME_TO_ID[name] = item_id
        classification = _guess_classification(name)
        return MC3Item(name, classification, item_id, self.player)

    def get_filler_item_name(self) -> str:
        return self.random.choice(filler_item_names)

    def create_regions(self) -> None:
        # Menu region (always created, per AP convention)
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)
        create_regions_from_catalog(self, self.catalog)

    def create_items(self) -> None:
        self.multiworld.itempool += build_item_pool(self, self.catalog)

    def set_rules(self) -> None:
        apply_rules_from_gate_contract(self, self.catalog)

    def fill_slot_data(self) -> Dict[str, object]:
        return build_slot_data(self, self.catalog)

    def generate_output(self, output_directory: str):
        write_seed_contract_json(self, output_directory)

    def _next_item_id(self) -> int:
        """Assign a new item ID."""
        base = 7160000
        existing = max(ITEM_NAME_TO_ID.values()) if ITEM_NAME_TO_ID else base
        new_id = existing + 1
        # Ensure we're above base
        if new_id < base:
            new_id = base + 1
        return new_id


def _guess_classification(name: str) -> ItemClassification:
    n = name.lower()
    if "trap:" in n:
        return ItemClassification.trap
    if "permit" in n or "license" in n or "grant" in n or "city " in n:
        return ItemClassification.progression
    if "money pack" in n:
        return ItemClassification.useful
    if "victory" in n:
        return ItemClassification.progression
    return ItemClassification.filler