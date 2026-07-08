"""Unit tests for the AP protocol layer — packet builders + resync state machine."""

import pytest

from mc3ap.adapters.archipelago.ap_protocol import (
    ReceivedItemsTracker,
    connect_packet,
    location_checks_packet,
    sync_packet,
)


def items_packet(index, item_ids):
    return {
        "cmd": "ReceivedItems",
        "index": index,
        "items": [{"item": i, "location": -1, "player": 1, "flags": 0} for i in item_ids],
    }


class TestPacketBuilders:
    def test_connect_packet_shape(self):
        p = connect_packet("Midnight Club 3: DUB Edition Remix", "Josh")
        assert p["cmd"] == "Connect"
        assert p["name"] == "Josh"
        assert p["version"]["class"] == "Version"
        assert p["items_handling"] == 0b111

    def test_location_checks_packet(self):
        assert location_checks_packet([1, 2, 3]) == {"cmd": "LocationChecks", "locations": [1, 2, 3]}

    def test_sync_packet(self):
        assert sync_packet() == {"cmd": "Sync"}


class TestReceivedItemsTracker:
    def test_sequential_delivery(self):
        t = ReceivedItemsTracker()
        r1 = t.apply(items_packet(0, [100, 101]))
        assert not r1.resync
        assert [i.item_id for i in r1.new_items] == [100, 101]
        assert t.next_index == 2

        r2 = t.apply(items_packet(2, [102]))
        assert not r2.resync
        assert [i.item_id for i in r2.new_items] == [102]
        assert t.next_index == 3
        assert len(t.inventory) == 3

    def test_index_zero_is_full_replacement(self):
        t = ReceivedItemsTracker()
        t.apply(items_packet(0, [1, 2, 3]))
        # Server resends full inventory from scratch (e.g. after reconnect)
        r = t.apply(items_packet(0, [9, 8]))
        assert not r.resync
        assert [i.item_id for i in t.inventory] == [9, 8]
        assert t.next_index == 2

    def test_gap_triggers_resync(self):
        t = ReceivedItemsTracker()
        t.apply(items_packet(0, [1, 2]))         # next_index now 2
        r = t.apply(items_packet(5, [7]))        # missed 2,3,4 -> resync
        assert r.resync
        assert r.new_items == []
        # inventory unchanged, awaiting Sync
        assert t.next_index == 2
        assert len(t.inventory) == 2

    def test_ap_index_is_monotonic_and_absolute(self):
        t = ReceivedItemsTracker()
        t.apply(items_packet(0, [10]))
        t.apply(items_packet(1, [11]))
        t.apply(items_packet(2, [12]))
        assert [i.ap_index for i in t.inventory] == [0, 1, 2]

    def test_duplicate_item_ids_are_kept_as_separate_instances(self):
        t = ReceivedItemsTracker()
        t.apply(items_packet(0, [5]))
        t.apply(items_packet(1, [5]))            # same item, second copy
        assert len(t.inventory) == 2
        assert all(i.item_id == 5 for i in t.inventory)
        assert [i.ap_index for i in t.inventory] == [0, 1]

    def test_resync_then_full_replacement_recovers(self):
        t = ReceivedItemsTracker()
        t.apply(items_packet(0, [1, 2]))
        assert t.apply(items_packet(9, [3])).resync   # gap
        # client sends Sync; server replies index=0 full inventory
        r = t.apply(items_packet(0, [1, 2, 3, 4]))
        assert not r.resync
        assert [i.item_id for i in t.inventory] == [1, 2, 3, 4]
        assert t.next_index == 4
