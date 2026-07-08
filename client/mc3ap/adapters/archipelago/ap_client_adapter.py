"""Archipelago websocket client adapter.

Speaks the AP network protocol over a websocket using only `websockets` +
JSON — no Archipelago Python package needed on the client side. The protocol
decisions live in ap_protocol.py (pure, tested); this class is the transport.

Connect handshake: on open the server sends RoomInfo; we reply Connect; the
server sends Connected (with slot_data) or ConnectionRefused.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from . import ap_protocol as proto

try:  # websockets is an optional extra ([ap])
    import websockets
except Exception:  # pragma: no cover
    websockets = None


class APConnectionError(RuntimeError):
    pass


class ArchipelagoClient:
    """Minimal AP websocket client.

    Usage:
        ap = ArchipelagoClient("Midnight Club 3: DUB Edition Remix")
        await ap.connect("wss://archipelago.gg:38281", "Josh")
        await ap.send_location_checks([7161001])
        new_items = await ap.poll()
    """

    def __init__(self, game: str, uuid: str = "mc3ap"):
        self.game = game
        self.uuid = uuid
        self._ws = None
        self._tracker = proto.ReceivedItemsTracker()
        self.slot_data: Dict[str, Any] = {}
        self.checked_locations: List[int] = []
        self._sent_checks: set[int] = set()

    # ── lifecycle ────────────────────────────────────────────────────────

    async def connect(self, url: str, slot_name: str, password: str = "") -> dict:
        if websockets is None:
            raise APConnectionError("The 'websockets' package is required (pip install .[ap])")
        self._ws = await websockets.connect(url, max_size=None)

        await self._recv_until("RoomInfo")
        await self._send(proto.connect_packet(self.game, slot_name, password, self.uuid))

        for pkt in await self._recv_any():
            if pkt["cmd"] == "Connected":
                self.slot_data = pkt.get("slot_data", {})
                self.checked_locations = pkt.get("checked_locations", [])
                return pkt
            if pkt["cmd"] == "ConnectionRefused":
                raise APConnectionError(f"Connection refused: {pkt.get('errors')}")
        raise APConnectionError("No Connected/ConnectionRefused after Connect")

    async def disconnect(self):
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    # ── outgoing ─────────────────────────────────────────────────────────

    async def send_location_checks(self, location_ids: List[int]):
        # Duplicates are safe per protocol; we still send whatever we're given.
        if location_ids:
            await self._send(proto.location_checks_packet(location_ids))
            self._sent_checks.update(location_ids)

    async def resend_all_checks(self):
        if self._sent_checks:
            await self._send(proto.location_checks_packet(sorted(self._sent_checks)))

    async def request_sync(self):
        await self._send(proto.sync_packet())

    async def send_goal(self):
        await self._send(proto.status_update_packet(proto.CLIENT_STATUS_GOAL))

    # ── incoming ─────────────────────────────────────────────────────────

    async def poll(self, timeout: Optional[float] = None) -> List[proto.ReceivedItem]:
        """Read one batch of server messages, apply items, handle resync.
        Returns any newly received items.

        With `timeout`, returns [] if no message arrives in that window instead
        of blocking — this keeps a single-threaded client loop responsive so it
        can also poll the game for checks between server messages.
        """
        new_items: List[proto.ReceivedItem] = []
        try:
            packets = await self._recv_any(timeout=timeout)
        except asyncio.TimeoutError:
            return []
        for pkt in packets:
            cmd = pkt.get("cmd")
            if cmd == "ReceivedItems":
                result = self._tracker.apply(pkt)
                if result.resync:
                    await self.request_sync()
                    await self.resend_all_checks()
                else:
                    new_items.extend(result.new_items)
            elif cmd == "RoomUpdate" and "checked_locations" in pkt:
                self.checked_locations = pkt["checked_locations"]
        return new_items

    @property
    def inventory(self) -> List[proto.ReceivedItem]:
        return list(self._tracker.inventory)

    # ── transport helpers ────────────────────────────────────────────────

    async def _send(self, packet: Dict[str, Any]):
        await self._ws.send(json.dumps([packet]))

    async def _recv_any(self, timeout: Optional[float] = None) -> List[Dict[str, Any]]:
        if timeout is None:
            raw = await self._ws.recv()
        else:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
        data = json.loads(raw)
        return data if isinstance(data, list) else [data]

    async def _recv_until(self, cmd: str) -> Dict[str, Any]:
        while True:
            for pkt in await self._recv_any():
                if pkt.get("cmd") == cmd:
                    return pkt
