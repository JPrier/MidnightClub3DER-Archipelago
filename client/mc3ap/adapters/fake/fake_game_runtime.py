"""Fake MC3 game runtime for integration testing.

Simulates the in-game state machine well enough to exercise
the full client pipeline without PCSX2 or a PS2 payload.

Models: cities, events, garage, parts, money, collectibles, and abilities
as a simple state machine that responds to commands and emits events.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, FrozenSet, List, Optional

from ...domain.ids import (
    AbilityId,
    CityId,
    CollectibleId,
    CosmeticId,
    EventId,
    GrantedVehicleInstance,
    ItemId,
    LocationId,
    PartId,
    VehicleCategory,
    VehicleClass,
    VehicleId,
)
from ...domain.model import (
    EventDefinition,
    GateDecisionType,
)
from ...domain.reducer import DesiredGameState


# ═══════════════════════════════════════════════════════════════════════════════
#  Tiny in-memory game world
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FakeGameRuntime:
    """A minimal MC3 simulation that obeys DesiredGameState."""

    # ── world state ───────────────────────────────────────────────────────────
    current_city: CityId = CityId("san_diego")
    current_event: Optional[EventId] = None
    current_vehicle: Optional[VehicleId] = None

    owned_vehicles: set[VehicleId] = field(default_factory=set)
    granted_vehicle_instances: set[GrantedVehicleInstance] = field(default_factory=set)
    garage_slots_used: int = 0
    garage_slot_limit: int = 30

    equipped_parts: set[PartId] = field(default_factory=set)
    owned_parts: set[PartId] = field(default_factory=set)

    money: int = 0
    collected_logos: set[CollectibleId] = field(default_factory=set)

    active_abilities: set[AbilityId] = field(default_factory=set)

    # ── event log ─────────────────────────────────────────────────────────────
    events: List[dict] = field(default_factory=list)

    # ── hooks ─────────────────────────────────────────────────────────────────
    on_event: Optional[Callable] = None
    on_location_checked: Optional[Callable[[LocationId], None]] = None

    # ── desired state mirror ──────────────────────────────────────────────────
    desired: Optional[DesiredGameState] = None

    # ══════════════════════════════════════════════════════════════════════════
    #  Commands (Python client → game)
    # ══════════════════════════════════════════════════════════════════════════

    def set_desired_state(self, desired: DesiredGameState):
        self.desired = desired
        self.garage_slot_limit = desired.garage_slot_limit
        self._emit("desired_state_applied", {"sequence": desired.sequence})

    def reconcile(self):
        """Apply desired state to runtime (repair pass)."""
        if self.desired is None:
            return

        # Money ledger
        self.money = self.desired.total_ap_money

        # Grant vehicles
        for gvi in self.desired.granted_vehicles:
            if gvi not in self.granted_vehicle_instances:
                # parse vehicle_id from "vehicle_id#ap_index"
                vid_str = gvi.split("#")[0]
                vid = VehicleId(vid_str)
                if self.garage_slots_used < self.garage_slot_limit:
                    self.owned_vehicles.add(vid)
                    self.garage_slots_used += 1
                    self.granted_vehicle_instances.add(gvi)
                    self._emit("vehicle_granted", {"instance": gvi})
                else:
                    self._emit("garage_full", {"pending": gvi})

        # Enforce part legality
        for part in list(self.equipped_parts):
            if part not in self.desired.allowed_parts and self.desired.allowed_parts:
                self.equipped_parts.discard(part)
                self._emit("part_repaired", {"part_id": part})

    # ══════════════════════════════════════════════════════════════════════════
    #  Game actions (simulated player)
    # ══════════════════════════════════════════════════════════════════════════

    def travel_to_city(self, city_id: CityId) -> bool:
        if self.desired and city_id not in self.desired.allowed_cities:
            self._emit("gate_blocked", {"gate": "city", "city": city_id})
            return False
        self.current_city = city_id
        self._emit("city_travelled", {"city": city_id})
        if city_id != CityId("san_diego"):
            self._emit_location_check(LocationId(f"city_unlocked_{city_id}"))
        return True

    def select_event(self, event_id: EventId):
        self.current_event = event_id
        self._emit("event_selected", {"event_id": event_id})

    def attempt_start_event(self, event_id: EventId) -> bool:
        if self.desired and event_id not in self.desired.allowed_events and self.desired.allowed_events:
            self._emit("gate_blocked", {"gate": "event", "event_id": event_id})
            return False
        self.current_event = event_id
        return True

    def complete_race(self, won: bool = True):
        if self.current_event is None:
            return
        if won:
            self._emit_location_check(LocationId(f"race_win_{self.current_event}"))
            self.money += 1000  # vanilla race prize
        self._emit("race_finished", {"event_id": self.current_event, "won": won})

    def purchase_vehicle(self, vehicle_id: VehicleId, price: int = 0) -> bool:
        if self.desired and self.desired.allowed_vehicles:
            if vehicle_id not in self.desired.allowed_vehicles:
                self._emit("gate_blocked", {"gate": "vehicle_purchase", "vehicle_id": vehicle_id})
                return False
        if self.garage_slots_used >= self.garage_slot_limit:
            self._emit("garage_full", {"pending": str(vehicle_id)})
            return False
        self.money -= price
        self.owned_vehicles.add(vehicle_id)
        self.garage_slots_used += 1
        self._emit_location_check(LocationId(f"vehicle_purchased_{vehicle_id}"))
        return True

    def collect_logo(self, collectible_id: CollectibleId) -> bool:
        if collectible_id in self.collected_logos:
            return False  # already collected
        self.collected_logos.add(collectible_id)
        self._emit_location_check(LocationId(f"logo_collected_{collectible_id}"))
        return True

    def activate_ability(self, ability_id: AbilityId) -> bool:
        if self.desired and ability_id not in self.desired.allowed_abilities and self.desired.allowed_abilities:
            self._emit("gate_blocked", {"gate": "ability", "ability_id": ability_id})
            return False
        self.active_abilities.add(ability_id)
        return True

    # ══════════════════════════════════════════════════════════════════════════
    #  Internals
    # ══════════════════════════════════════════════════════════════════════════

    def _emit(self, event_type: str, payload: dict):
        event = {"type": event_type, **payload}
        self.events.append(event)
        if self.on_event:
            self.on_event(event)

    def _emit_location_check(self, location_id: LocationId):
        self._emit("location_checked", {"location_id": location_id})
        if self.on_location_checked:
            self.on_location_checked(location_id)

    def snapshot(self) -> dict:
        """Return a RuntimeActualState-like dict."""
        return {
            "current_city": self.current_city,
            "current_event": self.current_event,
            "current_vehicle": self.current_vehicle,
            "owned_vehicles": frozenset(self.owned_vehicles),
            "equipped_parts": frozenset(self.equipped_parts),
            "owned_parts": frozenset(self.owned_parts),
            "collected_logos": frozenset(self.collected_logos),
            "money": self.money,
            "active_abilities": frozenset(self.active_abilities),
            "garage_slots_used": self.garage_slots_used,
            "garage_slot_limit": self.garage_slot_limit,
        }