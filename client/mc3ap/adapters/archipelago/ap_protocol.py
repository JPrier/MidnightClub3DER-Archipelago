"""Pure Archipelago protocol logic — packet building + ReceivedItems tracking.

No sockets here so the tricky index/resync rules are fully unit-testable.
Protocol facts encoded (from the AP network protocol + design doc §1.1):

  * Packets are JSON lists of command objects.
  * ReceivedItems carries a starting `index`; items are ordered.
  * index == 0 means a FULL inventory replacement — drop prior inventory.
  * If an incoming index != the next expected index, the client is out of
    sync: it must send Sync, then re-send all LocationChecks.
  * Duplicate LocationChecks are safe and used for resync.
  * The client keeps a monotonic received-item counter across restarts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── Outgoing packet builders ─────────────────────────────────────────────────

def connect_packet(game: str, slot_name: str, password: str = "",
                   uuid: str = "mc3ap", version: Tuple[int, int, int] = (0, 6, 4),
                   items_handling: int = 0b111, tags: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "cmd": "Connect",
        "game": game,
        "name": slot_name,
        "password": password,
        "uuid": uuid,
        "version": {"major": version[0], "minor": version[1], "build": version[2],
                    "class": "Version"},
        "items_handling": items_handling,
        "tags": tags or [],
        "slot_data": True,
    }


def location_checks_packet(location_ids: List[int]) -> Dict[str, Any]:
    return {"cmd": "LocationChecks", "locations": list(location_ids)}


def sync_packet() -> Dict[str, Any]:
    return {"cmd": "Sync"}


def status_update_packet(status: int) -> Dict[str, Any]:
    # ClientStatus: 10=CONNECTED, 20=READY, 30=PLAYING, 30==GOAL? AP uses 30 GOAL.
    return {"cmd": "StatusUpdate", "status": status}


CLIENT_STATUS_PLAYING = 20
CLIENT_STATUS_GOAL = 30


# ── Received-item tracking / resync state machine ────────────────────────────

@dataclass
class ReceivedItem:
    item_id: int
    location: int
    player: int
    flags: int
    ap_index: int          # absolute inventory index assigned by tracker


@dataclass
class ReceivedItemsTracker:
    """Applies ReceivedItems packets with correct ordering / resync rules.

    `next_index` is the count of items already accepted (== index the next
    packet must start at).
    """
    next_index: int = 0
    inventory: List[ReceivedItem] = field(default_factory=list)

    def apply(self, packet: Dict[str, Any]) -> "ApplyResult":
        """Consume one ReceivedItems packet. Returns what to do next."""
        assert packet.get("cmd") == "ReceivedItems"
        index = packet["index"]
        raw_items = packet.get("items", [])

        # Full inventory replacement.
        if index == 0:
            self.inventory = []
            self.next_index = 0
            new = self._append(raw_items)
            return ApplyResult(new_items=new, resync=False)

        # Out of order → we missed something: ask for a full resync.
        if index != self.next_index:
            return ApplyResult(new_items=[], resync=True)

        new = self._append(raw_items)
        return ApplyResult(new_items=new, resync=False)

    def _append(self, raw_items: List[Dict[str, Any]]) -> List[ReceivedItem]:
        added: List[ReceivedItem] = []
        for it in raw_items:
            item = ReceivedItem(
                item_id=it["item"],
                location=it.get("location", -1),
                player=it.get("player", 0),
                flags=it.get("flags", 0),
                ap_index=self.next_index,
            )
            self.inventory.append(item)
            self.next_index += 1
            added.append(item)
        return added


@dataclass
class ApplyResult:
    new_items: List[ReceivedItem]
    resync: bool           # caller should send Sync + re-send LocationChecks
