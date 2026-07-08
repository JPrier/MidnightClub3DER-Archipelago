"""Fake Archipelago server for integration testing.

Simulates the AP protocol well enough to exercise the full client pipeline:
  connect → receive items → send checks → goal detection
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ...domain.ids import ItemId, LocationId


@dataclass
class FakeAPServer:
    """In-memory AP server that responds to a single client."""

    seed_name: str = "test-seed"
    slot: int = 1
    slot_name: str = "TestPlayer"

    # pre-loaded data
    item_queue: List[tuple[int, ItemId]] = field(default_factory=list)  # (ap_index, item_id)
    goal_item_name: str = "Victory"

    # runtime state
    connected: bool = False
    location_checks_received: List[LocationId] = field(default_factory=list)
    goal_status_received: bool = False
    sync_requested: bool = False

    # hooks for scenario scripting
    on_connect: Optional[Callable] = None
    on_location_check: Optional[Callable[[LocationId], None]] = None

    # ── connection lifecycle ─────────────────────────────────────────────────

    async def connect(self, slot_name: str = "") -> dict:
        self.connected = True
        if self.on_connect:
            self.on_connect()
        return {
            "slot": self.slot,
            "slot_name": self.slot_name,
            "seed_name": self.seed_name,
            "players": [self.slot_name],
        }

    async def disconnect(self):
        self.connected = False

    # ── item delivery ────────────────────────────────────────────────────────

    async def receive_items(self) -> List[dict]:
        """Return queued items as ReceivedItems packets."""
        packets = []
        for ap_index, item_id in self.item_queue:
            packets.append({
                "cmd": "ReceivedItems",
                "index": ap_index,
                "items": [{
                    "item": item_id,
                    "location": -1,
                    "player": self.slot,
                    "flags": 0,
                    "class": 0,  # progression
                }],
            })
        self.item_queue.clear()
        return packets

    def queue_item(self, ap_index: int, item_id: ItemId):
        self.item_queue.append((ap_index, item_id))

    # ── location checks ──────────────────────────────────────────────────────

    async def send_location_checks(self, location_ids: List[LocationId]):
        self.location_checks_received.extend(location_ids)
        for lid in location_ids:
            if self.on_location_check:
                self.on_location_check(lid)

    # ── goal ──────────────────────────────────────────────────────────────────

    async def send_goal(self):
        self.goal_status_received = True

    # ── sync ──────────────────────────────────────────────────────────────────

    async def request_sync(self):
        self.sync_requested = True
        # return all items as index=0 (full inventory)
        return {
            "cmd": "ReceivedItems",
            "index": 0,
            "items": [
                {"item": iid, "location": -1, "player": self.slot, "flags": 0}
                for _, iid in sorted(self.item_queue)
            ],
        }