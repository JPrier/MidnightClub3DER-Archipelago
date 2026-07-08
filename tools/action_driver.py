"""Synchronous Action Driver — Phase A (Level 0-2, no MIPS dispatch needed).

Level 0 (stubs): Python writes synthetic events directly to mailbox event area.
Level 2 (state R/W): Python reads/writes confirmed EE memory fields directly.

No continuous hook needed. No MIPS dispatch needed.
For Levels 0-2, Python IS the action driver.
"""

import ctypes
import struct
import subprocess
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class Action(IntEnum):
    PING = 0x1000
    GET_MONEY = 0x3000
    SET_MONEY = 0x3001
    GET_POSITION = 0x3002
    GET_VEHICLE_LIST = 0x3003
    GET_HEARTBEAT = 0x3004
    FORCE_LOCATION_CHECK = 0x2000


# ── Confirmed memory map ─────────────────────────────────────────────────────

CONFIRMED = {
    "money":              0x00800870,
    "money_earned":       0x00800874,
    "player_race_position": 0x007CA044,
    "profile_ptr":        0x00619B14,
    "vehicle_list_ptr":   0x006E0170,
    "mailbox_heartbeat":  0x0072000C,
    "mailbox_build_id":   0x00720004,
    "event_catalog_ptr":  0x00800878,
}


class MC3LiveAPI:
    """Direct EE memory read/write — no PNACH dispatch needed."""

    def __init__(self):
        # Find PCSX2 and EE base via mailbox
        from run_explore import LiveConnection
        self._mc3 = LiveConnection()
        self._ee = self._mc3._ee_base
        self._mb = self._mc3._mb_host

    def close(self):
        self._mc3.close()

    def _rd(self, ee):
        return self._mc3.read_u32(ee)

    def _wr(self, ee, val):
        self._mc3.write_u32(ee, val)

    # ── Level 0: Synthetic actions ──────────────────────────────────────

    def ping(self) -> bool:
        """Always returns True — proves Python↔EE connection."""
        magic = self._rd(0x00720000)
        return magic == 0x4133434D  # "MC3A"

    def ping_result(self) -> dict:
        return {"action": "PING", "ok": self.ping(), "build_id": self._rd(CONFIRMED["mailbox_build_id"])}

    def force_location_check(self, location_id: int) -> dict:
        """Write a synthetic LocationChecked event to the mailbox."""
        # Write to a debug event area
        self._wr(0x00720300, int(Action.FORCE_LOCATION_CHECK))
        self._wr(0x00720304, location_id)
        self._wr(0x00720308, int(time.time() * 1000) & 0xFFFFFFFF)
        return {"action": "FORCE_LOCATION_CHECK", "location_id": location_id, "ok": True}

    # ── Level 2: Confirmed field read ───────────────────────────────────

    def get_money(self) -> dict:
        val = self._rd(CONFIRMED["money"])
        return {"action": "GET_MONEY", "money": val, "address": f"0x{CONFIRMED['money']:08X}"}

    def set_money(self, amount: int) -> dict:
        self._wr(CONFIRMED["money"], amount)
        verify = self._rd(CONFIRMED["money"])
        return {"action": "SET_MONEY", "written": amount, "verified": verify, "ok": verify == amount}

    def get_race_position(self) -> dict:
        val = self._rd(CONFIRMED["player_race_position"])
        return {"action": "GET_POSITION", "position": val, "is_first": val == 1}

    def get_vehicle_list(self, max_count: int = 10) -> dict:
        """Read vehicle names from the vehicle array."""
        vl_ptr = self._rd(CONFIRMED["vehicle_list_ptr"])
        vehicles = []
        for i in range(max_count):
            addr = vl_ptr + i * 0x54  # stride 0x54
            name_ptr = self._rd(addr)
            if not (0x00500000 < name_ptr < 0x02000000):
                break
            try:
                name = self._mc3.read_string(name_ptr, 32)
            except:
                break
            if name and len(name) > 2:
                vehicles.append({"index": i, "name": name, "addr": f"0x{addr:08X}"})
        return {"action": "GET_VEHICLE_LIST", "count": len(vehicles), "vehicles": vehicles}

    def get_heartbeat(self) -> dict:
        val = self._rd(CONFIRMED["mailbox_heartbeat"])
        return {"action": "GET_HEARTBEAT", "heartbeat": val}

    # ── Snapshot ────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Full snapshot of all confirmed fields."""
        return {
            "money": self._rd(CONFIRMED["money"]),
            "money_earned": self._rd(CONFIRMED["money_earned"]),
            "race_position": self._rd(CONFIRMED["player_race_position"]),
            "profile_ptr": f"0x{self._rd(CONFIRMED['profile_ptr']):08X}",
            "vehicle_list_ptr": f"0x{self._rd(CONFIRMED['vehicle_list_ptr']):08X}",
            "heartbeat": self._rd(CONFIRMED["mailbox_heartbeat"]),
            "build_id": self._rd(CONFIRMED["mailbox_build_id"]),
        }


# ── Test ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("MC3AP Live API — Phase A (Level 0-2)")
    api = MC3LiveAPI()

    print("\n=== PING ===")
    r = api.ping_result()
    print(f"  ok={r['ok']} build_id={r['build_id']}")

    print("\n=== MONEY ===")
    r = api.get_money()
    print(f"  money={r['money']}")

    r = api.set_money(8888)
    print(f"  set 8888: written={r['written']} verified={r['verified']} ok={r['ok']}")

    r = api.set_money(6600)
    print(f"  restored 6600: ok={r['ok']}")

    print("\n=== RACE POSITION ===")
    r = api.get_race_position()
    print(f"  position={r['position']} first={r['is_first']}")

    print("\n=== VEHICLES ===")
    r = api.get_vehicle_list(5)
    print(f"  {r['count']} vehicles:")
    for v in r["vehicles"]:
        print(f"    [{v['index']}] {v['name']}")

    print("\n=== SNAPSHOT ===")
    s = api.snapshot()
    for k, v in s.items():
        print(f"  {k}: {v}")

    print("\n=== FORCE LOCATION CHECK ===")
    r = api.force_location_check(874030001)
    print(f"  {r}")

    api.close()