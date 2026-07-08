"""Catalog loader for the APWorld.

Loads the canonical game catalog from JSON data files.
In starter mode, returns a minimal catalog with only verified facts.
"""

import json
import os
from typing import Any, Dict

from .options import CatalogMode


class CatalogProxy:
    """Thin wrapper around loaded catalog data.

    The real types live in client/mc3ap/domain/; this proxy exists
    so the APWorld can reference catalog data without depending on
    the client package at generation time.
    """

    def __init__(self, data: Dict[str, Any]):
        self._data = data
        self.cities = _CityProxy.wrap_all(data.get("cities", {}))
        self.vehicles = _VehicleProxy.wrap_all(data.get("vehicles", {}))
        self.parts = _PartProxy.wrap_all(data.get("parts", {}))
        self.events = _EventProxy.wrap_all(data.get("events", {}))
        self.tournaments = data.get("tournaments", {})
        self.clubs = data.get("clubs", {})
        self.abilities = data.get("abilities", {})
        self.collectibles = data.get("collectibles", {})
        self.reward_rules = data.get("reward_rules", {})
        self.gate_table = data.get("gate_table", {})

        # Derived indexes
        self.events_by_city: Dict[str, set] = {}
        for eid, evt in self.events.items():
            city = getattr(evt, 'city', None)
            if city:
                self.events_by_city.setdefault(city, set()).add(eid)

    def event_ids(self):
        return frozenset(self.events.keys())

    def vehicle_ids(self):
        return frozenset(self.vehicles.keys())

    def part_ids(self):
        return frozenset(self.parts.keys())


class _CityProxy:
    def __init__(self, data: dict):
        self.city_id = data.get("city_id", "")
        self.name = data.get("name", "")
        self.is_starting = data.get("is_starting", False)

    @classmethod
    def wrap_all(cls, data: dict) -> dict:
        return {k: cls(v) for k, v in data.items()}


class _VehicleProxy:
    def __init__(self, data: dict):
        self.vehicle_id = data.get("vehicle_id", "")
        self.name = data.get("name", "")
        self.manufacturer = data.get("manufacturer", "")
        self.vehicle_class = data.get("vehicle_class", "")
        self.vehicle_category = data.get("vehicle_category", "")
        self.is_prize_car = data.get("is_prize_car", False)
        self.is_purchasable = data.get("is_purchasable", True)
        self.price = data.get("price", 0)

    @classmethod
    def wrap_all(cls, data: dict) -> dict:
        return {k: cls(v) for k, v in data.items()}


class _PartProxy:
    def __init__(self, data: dict):
        self.part_id = data.get("part_id", "")
        self.name = data.get("name", "")
        self.category = data.get("category", "")
        self.tier = data.get("tier", 0)
        self.price = data.get("price", 0)
        self.is_visual = data.get("is_visual", False)

    @classmethod
    def wrap_all(cls, data: dict) -> dict:
        return {k: cls(v) for k, v in data.items()}


class _EventProxy:
    def __init__(self, data: dict):
        self.event_id = data.get("event_id", "")
        self.name = data.get("name", "")
        self.city = data.get("city", "")
        self.race_type = data.get("race_type", "")
        self.class_requirement = data.get("class_requirement")
        self.category_requirement = data.get("category_requirement")
        self.is_tournament_race = data.get("is_tournament_race", False)
        self.is_club_race = data.get("is_club_race", False)

    @classmethod
    def wrap_all(cls, data: dict) -> dict:
        return {k: cls(v) for k, v in data.items()}


def load_catalog(mode_option: CatalogMode) -> CatalogProxy:
    """Load the game catalog based on the catalog mode option.

    CatalogMode:
      - starter (0): minimal verified catalog
      - curated (1): manually-curated full catalog
      - generated (2): extracted from ASSETS.DAT + runtime probes
    """
    mode = mode_option.value if hasattr(mode_option, 'value') else 0

    if mode == 0:
        return _load_starter_catalog()
    elif mode == 1:
        return _load_json_catalog("curated_catalog.json")
    elif mode == 2:
        return _load_json_catalog("generated_catalog.json")
    return _load_starter_catalog()


def _load_starter_catalog() -> CatalogProxy:
    """Minimal catalog with only verified static facts."""
    return CatalogProxy({
        "cities": {
            "san_diego": {"city_id": "san_diego", "name": "San Diego", "is_starting": True},
            "atlanta":   {"city_id": "atlanta", "name": "Atlanta"},
            "detroit":   {"city_id": "detroit", "name": "Detroit"},
            "tokyo":     {"city_id": "tokyo", "name": "Tokyo"},
        },
        "abilities": {
            "zone": {"ability_id": "zone", "name": "Zone"},
            "agro": {"ability_id": "agro", "name": "Agro"},
            "roar": {"ability_id": "roar", "name": "Roar"},
        },
        "vehicles": {},
        "parts": {},
        "events": {},
        "tournaments": {},
        "clubs": {},
        "collectibles": {},
        "reward_rules": {},
        "gate_table": {},
    })


def _load_json_catalog(filename: str) -> CatalogProxy:
    """Load a catalog from a JSON file in the data directory."""
    data_dir = os.path.join(os.path.dirname(__file__), "data", "generated_catalog")
    path = os.path.join(data_dir, filename)
    if not os.path.exists(path):
        # Fall back to starter
        return _load_starter_catalog()
    with open(path, encoding="utf-8") as f:
        return CatalogProxy(json.load(f))