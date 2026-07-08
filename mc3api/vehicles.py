"""Vehicle catalog reader.

The game builds a vehicle array (pointer at MAP.vehicle_list_ptr) from
tune/vehicle/vehicle.lst. Entries are 0x54 bytes; +0x00 is a pointer to the
null-terminated vehicle name (e.g. 'vp_eclipse_04').
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List


VEHICLE_STRIDE = 0x54
MAX_VEHICLES = 128  # Remix ships 94; leave headroom


@dataclass(frozen=True)
class Vehicle:
    index: int
    ee_addr: int      # address of the vehicle struct
    name_ptr: int
    name: str


def _valid_ee_ptr(p: int) -> bool:
    return 0x00100000 < p < 0x02000000


def parse_vehicle_array(raw: bytes, base_addr: int, name_resolver) -> List[Vehicle]:
    """Parse the vehicle array from raw bytes. Pure apart from name_resolver.

    name_resolver(ee_addr) -> str reads a c-string at an EE address.
    Stops at the first entry whose name pointer is invalid.
    """
    vehicles: List[Vehicle] = []
    for i in range(MAX_VEHICLES):
        off = i * VEHICLE_STRIDE
        if off + 4 > len(raw):
            break
        name_ptr = struct.unpack_from("<I", raw, off)[0]
        if not _valid_ee_ptr(name_ptr):
            break
        name = name_resolver(name_ptr)
        if not name or not name.isprintable():
            break
        vehicles.append(Vehicle(index=i, ee_addr=base_addr + off, name_ptr=name_ptr, name=name))
    return vehicles


def read_vehicles(bridge, memmap) -> List[Vehicle]:
    base = bridge.read_u32(memmap.vehicle_list_ptr)
    if not _valid_ee_ptr(base):
        return []
    raw = bridge.read(base, MAX_VEHICLES * VEHICLE_STRIDE)
    return parse_vehicle_array(raw, base, lambda p: bridge.read_cstring(p, 32))
