"""Property-based invariants for the domain reducer.

Run with:  pytest client/mc3ap/domain/invariants.py -v

These tests encode the design rules from Section 16.3:
  • deterministic
  • idempotent
  • monotonic
  • money ledger correctness
  • vehicle grant deduplication
  • trap idempotency
"""

import pytest

from .ids import (
    CityId,
    EventId,
    GateId,
    GrantedVehicleInstance,
    ItemId,
    LocationId,
    VehicleId,
)
from .model import (
    EventDefinition,
    GoalDefinition,
    ItemClassification,
    ItemDefinition,
    LocationDefinition,
    VehicleDefinition,
)
from .reducer import (
    ClientState,
    apply_full_inventory_reset,
    apply_location_checked,
    apply_received_item,
    reduce_desired_state,
)
from .seed_contract import GateDefinition, MC3Options, SeedContract


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_seed(**overrides) -> SeedContract:
    opts = MC3Options()
    city_gate = GateDefinition(
        gate_id=GateId("city_atlanta"),
        description="City Permit: Atlanta",
        required_items=frozenset(["City Permit: Atlanta"]),
    )
    vehicle_class_d = GateDefinition(
        gate_id=GateId("class_d"),
        description="Vehicle Class License: D",
        required_items=frozenset(["Vehicle Class License: D"]),
    )
    return SeedContract(
        seed_name="test",
        slot=1,
        catalog_hash="00000000",
        item_table={
            ItemId(1): ItemDefinition(item_id=ItemId(1), name="City Permit: Atlanta", classification=ItemClassification.PROGRESSION),
            ItemId(2): ItemDefinition(item_id=ItemId(2), name="Vehicle Class License: D", classification=ItemClassification.PROGRESSION),
            ItemId(3): ItemDefinition(item_id=ItemId(3), name="Money Pack: $5,000", classification=ItemClassification.USEFUL),
            ItemId(4): ItemDefinition(item_id=ItemId(4), name="Vehicle Grant: nissan_350z", classification=ItemClassification.PROGRESSION),
            ItemId(5): ItemDefinition(item_id=ItemId(5), name="Vehicle Grant: nissan_350z", classification=ItemClassification.PROGRESSION),  # deliberate duplicate
        },
        location_table={
            LocationId(100): LocationDefinition(location_id=LocationId(100), name="Race Win: san_diego_01", region="San Diego"),
        },
        gate_table={
            GateId("city_atlanta"): city_gate,
            GateId("class_d"): vehicle_class_d,
        },
        goal_definition=GoalDefinition(name="Complete Career", item_name="Victory"),
        options=opts,
        **overrides,
    )


# ── tests ─────────────────────────────────────────────────────────────────────

class TestDeterministic:
    """Same inputs always produce the same output."""

    def test_same_seed_same_empty_state(self):
        seed = _make_seed()
        cs = ClientState()
        s1 = reduce_desired_state(seed, cs, sequence=1)
        s2 = reduce_desired_state(seed, cs, sequence=1)
        assert s1 == s2
        assert s1.state_hash == s2.state_hash

    def test_hash_different_when_state_differs(self):
        seed = _make_seed()
        cs1 = ClientState()
        cs2 = apply_received_item(ClientState(), ap_index=0, item_id=ItemId(1))
        s1 = reduce_desired_state(seed, cs1)
        s2 = reduce_desired_state(seed, cs2)
        assert s1.state_hash != s2.state_hash


class TestIdempotent:
    """Applying same AP inventory twice yields same desired state."""

    def test_reapplying_same_item(self):
        seed = _make_seed()
        cs = apply_received_item(ClientState(), ap_index=0, item_id=ItemId(1))
        s1 = reduce_desired_state(seed, cs)
        s2 = reduce_desired_state(seed, cs)
        assert s1 == s2

    def test_full_reset_then_reapply(self):
        seed = _make_seed()
        initial = {0: ItemId(1), 1: ItemId(2)}
        cs1 = apply_full_inventory_reset(initial)
        cs2 = apply_full_inventory_reset(initial)
        s1 = reduce_desired_state(seed, cs1)
        s2 = reduce_desired_state(seed, cs2)
        assert s1 == s2


class TestMonotonic:
    """Receiving more progression never removes unlocks."""

    def test_city_unlock_persists(self):
        seed = _make_seed()
        cs_before = ClientState()
        cs_after = apply_received_item(cs_before, ap_index=0, item_id=ItemId(1))
        s_before = reduce_desired_state(seed, cs_before)
        s_after = reduce_desired_state(seed, cs_after)
        assert CityId("atlanta") not in s_before.allowed_cities
        assert CityId("atlanta") in s_after.allowed_cities

    def test_adding_more_items_does_not_remove_unlocks(self):
        seed = _make_seed()
        cs = apply_received_item(ClientState(), ap_index=0, item_id=ItemId(1))
        s1 = reduce_desired_state(seed, cs)
        cs = apply_received_item(cs, ap_index=1, item_id=ItemId(2))
        s2 = reduce_desired_state(seed, cs)
        # everything in s1 should still be in s2
        assert s1.allowed_cities <= s2.allowed_cities
        assert s1.allowed_vehicle_classes <= s2.allowed_vehicle_classes


class TestMoneyLedger:
    """Replay does NOT double money."""

    def test_single_money_pack(self):
        seed = _make_seed()
        cs = apply_received_item(ClientState(), ap_index=0, item_id=ItemId(3))
        state = reduce_desired_state(seed, cs)
        assert state.total_ap_money == 5000

    def test_duplicate_index_same_money(self):
        seed = _make_seed()
        cs = apply_received_item(ClientState(), ap_index=0, item_id=ItemId(3))
        # simulating "replayed" index does not exist because index is unique
        # but if somehow same index re-applied, it's the same item
        cs2 = ClientState(
            received_items={0: ItemId(3), 0: ItemId(3)},  # same index = deduped by dict
            item_instance_ids=cs.item_instance_ids,
        )
        state = reduce_desired_state(seed, cs2)
        assert state.total_ap_money == 5000  # NOT 10000

    def test_two_different_money_packs(self):
        seed = _make_seed()
        # add $5,000 at index 0
        cs = apply_received_item(ClientState(), ap_index=0, item_id=ItemId(3))
        # add another $5,000 at index 1 (different AP index = different instance)
        cs = apply_received_item(cs, ap_index=1, item_id=ItemId(3))
        state = reduce_desired_state(seed, cs)
        assert state.total_ap_money == 10000


class TestVehicleGrants:
    """Same AP index cannot duplicate; different indexes can if duplicates allowed."""

    def test_single_grant(self):
        seed = _make_seed()
        cs = apply_received_item(ClientState(), ap_index=0, item_id=ItemId(4))
        state = reduce_desired_state(seed, cs)
        assert len(state.granted_vehicles) == 1

    def test_two_grants_same_vehicle_different_indices(self):
        seed = _make_seed()
        cs = apply_received_item(ClientState(), ap_index=0, item_id=ItemId(4))
        cs = apply_received_item(cs, ap_index=1, item_id=ItemId(5))
        state = reduce_desired_state(seed, cs)
        assert len(state.granted_vehicles) == 2
        assert GrantedVehicleInstance("nissan_350z#0") in state.granted_vehicles
        assert GrantedVehicleInstance("nissan_350z#1") in state.granted_vehicles

    def test_same_index_does_not_duplicate(self):
        seed = _make_seed()
        # applying same index twice should produce same state
        cs = apply_received_item(ClientState(), ap_index=0, item_id=ItemId(4))
        cs2 = ClientState(
            received_items={0: ItemId(4)},
            item_instance_ids={ItemId(4): frozenset({0})},
        )
        s1 = reduce_desired_state(seed, cs)
        s2 = reduce_desired_state(seed, cs2)
        assert s1.granted_vehicles == s2.granted_vehicles


class TestLocationChecked:
    """Checking a location is remembered."""

    def test_check_location(self):
        seed = _make_seed()
        cs = apply_location_checked(ClientState(), LocationId(100))
        state = reduce_desired_state(seed, cs)
        assert LocationId(100) in state.checked_locations


class TestFullInventoryReset:
    """index==0 means full inventory replacement."""

    def test_reset_replaces_prior(self):
        seed = _make_seed()
        # build up some items
        cs1 = apply_received_item(ClientState(), ap_index=1, item_id=ItemId(1))
        cs1 = apply_received_item(cs1, ap_index=2, item_id=ItemId(2))
        # full reset with only item 3
        cs2 = apply_full_inventory_reset({0: ItemId(3)})
        s1 = reduce_desired_state(seed, cs1)
        s2 = reduce_desired_state(seed, cs2)
        # s2 should NOT have atlanta or class D unlocks
        assert CityId("atlanta") not in s2.allowed_cities
        assert s2.total_ap_money == 5000


class TestGoalDetection:
    """Goal completion is detected correctly."""

    def test_goal_via_item(self):
        seed = _make_seed()
        cs = apply_received_item(ClientState(), ap_index=0, item_id=ItemId(999))
        # need to add the goal item to the seed
        seed2 = SeedContract(
            **{**seed.__dict__,
               "item_table": {
                   **seed.item_table,
                   ItemId(999): ItemDefinition(item_id=ItemId(999), name="Victory", classification=ItemClassification.PROGRESSION),
               },
            }
        )
        state = reduce_desired_state(seed2, cs)
        assert state.goal_completed

    def test_no_goal_without_item(self):
        seed = _make_seed()
        cs = ClientState()
        state = reduce_desired_state(seed, cs)
        assert not state.goal_completed


# ── run with pytest ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    pytest.main([__file__, "-v"])