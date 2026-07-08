"""End-to-end test of ArchipelagoClient against a real in-process websocket
server that mimics the AP handshake + protocol. No emulator, no external AP.
"""

import asyncio
import json

import pytest

websockets = pytest.importorskip("websockets")

from mc3ap.adapters.archipelago.ap_client_adapter import APConnectionError, ArchipelagoClient


class MiniAPServer:
    """Scripted AP server: RoomInfo -> Connected -> then replays a script."""

    def __init__(self, script, refuse=False):
        self.script = script            # list of outgoing packet-lists after Connect
        self.refuse = refuse
        self.received = []              # packets the client sent
        self.location_checks = []

    async def handler(self, ws):
        await ws.send(json.dumps([{"cmd": "RoomInfo", "version": {"major": 0, "minor": 6, "build": 4}}]))
        # Expect Connect
        connect = json.loads(await ws.recv())[0]
        self.received.append(connect)
        assert connect["cmd"] == "Connect"
        if self.refuse:
            await ws.send(json.dumps([{"cmd": "ConnectionRefused", "errors": ["InvalidSlot"]}]))
            return
        await ws.send(json.dumps([{
            "cmd": "Connected", "slot": 1, "slot_data": {"goal": "city_champion"},
            "checked_locations": [],
        }]))
        # Replay scripted server messages, reading client packets in between.
        for outgoing in self.script:
            await ws.send(json.dumps(outgoing))
        # Drain anything the client sends (checks / sync) for a moment.
        try:
            while True:
                pkt = json.loads(await asyncio.wait_for(ws.recv(), timeout=0.2))[0]
                self.received.append(pkt)
                if pkt["cmd"] == "LocationChecks":
                    self.location_checks.extend(pkt["locations"])
        except (asyncio.TimeoutError, websockets.ConnectionClosed):
            pass


async def _serve(server):
    return await websockets.serve(server.handler, "127.0.0.1", 0)


def _url(ws_server):
    sock = list(ws_server.sockets)[0]
    return f"ws://127.0.0.1:{sock.getsockname()[1]}"


@pytest.mark.asyncio
async def test_connect_and_receive_items():
    server = MiniAPServer(script=[[{
        "cmd": "ReceivedItems", "index": 0,
        "items": [{"item": 7160001, "location": -1, "player": 1, "flags": 1}],
    }]])
    ws_server = await _serve(server)
    try:
        client = ArchipelagoClient("Midnight Club 3: DUB Edition Remix")
        connected = await client.connect(_url(ws_server), "Josh")
        assert connected["slot_data"]["goal"] == "city_champion"
        new = await client.poll()
        assert [i.item_id for i in new] == [7160001]
        await client.send_location_checks([7161001])
        await asyncio.sleep(0.05)
        await client.disconnect()
    finally:
        ws_server.close()
        await ws_server.wait_closed()
    assert 7161001 in server.location_checks


@pytest.mark.asyncio
async def test_connection_refused_raises():
    server = MiniAPServer(script=[], refuse=True)
    ws_server = await _serve(server)
    try:
        client = ArchipelagoClient("Midnight Club 3: DUB Edition Remix")
        with pytest.raises(APConnectionError):
            await client.connect(_url(ws_server), "BadSlot")
    finally:
        ws_server.close()
        await ws_server.wait_closed()


@pytest.mark.asyncio
async def test_gap_triggers_sync_and_check_resend():
    # Server sends an out-of-order ReceivedItems (index 5) after index 0..1,
    # forcing the client to Sync and resend its checks.
    server = MiniAPServer(script=[
        [{"cmd": "ReceivedItems", "index": 0,
          "items": [{"item": 1, "location": -1, "player": 1, "flags": 0}]}],
        [{"cmd": "ReceivedItems", "index": 5,
          "items": [{"item": 2, "location": -1, "player": 1, "flags": 0}]}],
    ])
    ws_server = await _serve(server)
    try:
        client = ArchipelagoClient("Midnight Club 3: DUB Edition Remix")
        await client.connect(_url(ws_server), "Josh")
        await client.send_location_checks([7161001, 7161002])
        await client.poll()   # index 0 -> 1 item
        await client.poll()   # index 5 -> resync path (Sync + resend checks)
        await asyncio.sleep(0.1)
        await client.disconnect()
    finally:
        ws_server.close()
        await ws_server.wait_closed()
    cmds = [p["cmd"] for p in server.received]
    assert "Sync" in cmds
    # checks were resent during resync
    assert server.location_checks.count(7161001) >= 2
