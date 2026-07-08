"""MC3AP Live Modding API — read and manipulate MC3 game state in real-time.

Connects to a running PCSX2 instance via process memory bridge.
Provides Pythonic access to game memory for testing and development.

Usage:
    from tools.mc3_api import MC3API
    mc3 = MC3API.connect()
    
    # Read game state
    print(mc3.profile_ptr)
    print(mc3.vehicle_list)
    print(mc3.vehicle_names[:5])
    
    # Write game state
    mc3.write_u32(0x0072000C, 0x2A)
    
    # Read raw memory
    data = mc3.read(0x007D2310, 256)
    
    # Hook testing
    addr = mc3.write_jal(0x004AE100, 0x007200A0)  # patch JAL, return original
    mc3.restore_jal(0x004AE100, addr)              # restore original
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import struct
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ── Constants ────────────────────────────────────────────────────────────────

# Known EE addresses (verified against SLUS-21355 / CRC 0x60A42FF5)
ADDR_PROFILE_PTR   = 0x00619B14  # pProfile — points to career profile
ADDR_VEH_LIST_PTR  = 0x006E0170  # ppVehList — points to vehicle array
ADDR_VEH_COUNT     = 0x006E0174  # pVehCount — number of vehicles

# Mailbox
ADDR_MAILBOX       = 0x00720000
MAILBOX_MAGIC      = 0x4133434D  # "MC3A"

# Verified JAL call sites (original targets from ELF analysis)
HOOK_CAREER_LOAD   = (0x001B0C20, 0x0C06C624, 0x001B1890)  # addr, orig_instr, target
HOOK_SET_CAR_CFG   = (0x004AE100, 0x0C1748E0, 0x005D2380)

# Hook addresses with unknown instruction types (need function entry discovery)
HOOK_RACE_FINISHED = 0x003EDAC8
HOOK_RACE_OVER     = 0x003EE860
HOOK_SAVE_1        = 0x001AE8A0
HOOK_SAVE_2        = 0x001AF4F8
HOOK_CREATE_SAVE   = 0x001AF098


# ── Windows API ──────────────────────────────────────────────────────────────

class _WinAPI:
    """Thin Windows API wrapper for process memory access."""

    def __init__(self, pid: int):
        self._k32 = ctypes.windll.kernel32
        self._h = self._k32.OpenProcess(0x0010 | 0x0020 | 0x0400, False, pid)
        if not self._h:
            raise RuntimeError(f"Cannot open PID {pid}")

        self._ReadProcessMemory = self._k32.ReadProcessMemory
        self._ReadProcessMemory.argtypes = [
            ctypes.wintypes.HANDLE, ctypes.wintypes.LPCVOID,
            ctypes.wintypes.LPVOID, ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self._ReadProcessMemory.restype = ctypes.wintypes.BOOL

        self._WriteProcessMemory = self._k32.WriteProcessMemory
        self._WriteProcessMemory.argtypes = [
            ctypes.wintypes.HANDLE, ctypes.wintypes.LPVOID,
            ctypes.wintypes.LPCVOID, ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self._WriteProcessMemory.restype = ctypes.wintypes.BOOL

    def close(self):
        if self._h:
            self._k32.CloseHandle(self._h)
            self._h = None

    def read(self, addr: int, size: int) -> bytes:
        buf = ctypes.create_string_buffer(size)
        br = ctypes.c_size_t()
        ok = self._ReadProcessMemory(self._h, ctypes.c_void_p(addr), buf, size, ctypes.byref(br))
        if not ok:
            raise OSError(f"ReadProcessMemory failed at 0x{addr:X}")
        return buf.raw[:br.value]

    def write(self, addr: int, data: bytes):
        buf = ctypes.create_string_buffer(data)
        bw = ctypes.c_size_t()
        ok = self._WriteProcessMemory(self._h, ctypes.c_void_p(addr), buf, len(data), ctypes.byref(bw))
        if not ok:
            raise OSError(f"WriteProcessMemory failed at 0x{addr:X}")
        return bw.value

    @staticmethod
    def find_pcsx2_pid() -> Optional[int]:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq pcsx2-qt.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True,
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.replace('"', "").split(",")
            if len(parts) >= 2 and "pcsx2-qt.exe" in parts[0]:
                try:
                    return int(parts[1])
                except ValueError:
                    pass
        return None


# ── Mailbox discovery ────────────────────────────────────────────────────────

def _find_mailbox(api: _WinAPI) -> int:
    """Scan PCSX2 memory for the mailbox marker + CRC pattern."""
    import ctypes as ct

    class MBI(ct.Structure):
        _fields_ = [
            ("BaseAddress", ct.c_void_p), ("AllocationBase", ct.c_void_p),
            ("AllocationProtect", ctypes.wintypes.DWORD), ("PartitionId", ctypes.wintypes.WORD),
            ("RegionSize", ct.c_size_t), ("State", ctypes.wintypes.DWORD),
            ("Protect", ctypes.wintypes.DWORD), ("Type", ctypes.wintypes.DWORD),
        ]

    VQE = api._k32.VirtualQueryEx
    VQE.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPCVOID, ct.POINTER(MBI), ct.c_size_t]
    VQE.restype = ct.c_size_t

    mbi = MBI()
    addr = ct.c_void_p(0)
    marker = b"MC3A"
    crc_bytes = struct.pack("<I", 0x60A42FF5)
    buf = ct.create_string_buffer(256 * 1024)
    br = ct.c_size_t()

    while True:
        r = VQE(api._h, addr, ct.byref(mbi), ct.sizeof(mbi))
        if r == 0:
            break
        if mbi.State == 0x1000 and mbi.RegionSize >= 4096:
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize
            for offset in range(0, min(size, 10 * 1024 * 1024), len(buf)):
                chunk = min(len(buf), size - offset)
                ok = api._ReadProcessMemory(api._h, ct.c_void_p(base + offset), buf, chunk, ct.byref(br))
                if not ok or br.value < 16:
                    break
                idx = 0
                while True:
                    idx = buf.raw.find(marker, idx)
                    if idx < 0:
                        break
                    if idx + 12 <= br.value and buf.raw[idx + 8:idx + 12] == crc_bytes:
                        return base + offset + idx
                    idx += 1
        nxt = (mbi.BaseAddress or 0) + mbi.RegionSize
        if nxt <= (addr.value or 0):
            break
        addr = ct.c_void_p(nxt)

    raise RuntimeError("Mailbox not found — is 60A42FF5.pnach loaded?")


# ── Vehicle discovery ─────────────────────────────────────────────────────────

@dataclass
class Vehicle:
    """A discovered vehicle in the game's vehicle list."""
    index: int
    ee_addr: int         # address of mcVehicle struct
    name_ptr: int        # pointer to name string
    name: str


def _discover_vehicles(api: _WinAPI, ee_base: int, veh_list_addr: int) -> List[Vehicle]:
    """Read the vehicle list from game memory."""
    vehicles = []
    ptr = _read_u32(api, ee_base + veh_list_addr)
    count = _read_u32(api, ee_base + ADDR_VEH_COUNT)

    if not (0x00100000 < ptr < 0x02000000):
        return vehicles

    # Walk the vehicle array
    for i in range(min(count, 100)):
        veh_struct = ptr + i * 0x20  # mcVehicle is roughly 0x20 bytes (estimated)
        name_ptr = _read_u32(api, ee_base + veh_struct)
        if not (0x00100000 < name_ptr < 0x02000000):
            continue

        name = _read_string(api, ee_base + name_ptr, 32)
        if name:
            vehicles.append(Vehicle(
                index=i, ee_addr=veh_struct,
                name_ptr=name_ptr, name=name,
            ))

    return vehicles


# ── Memory profile / snapshot ────────────────────────────────────────────────

@dataclass
class GameSnapshot:
    """Complete snapshot of discoverable game state."""
    profile_ptr: int
    vehicle_list_ptr: int
    vehicle_count: int
    vehicles: List[Vehicle]
    mailbox_build_id: int
    mailbox_heartbeat: int
    profile_first_256: bytes


# ── Helpers ──────────────────────────────────────────────────────────────────

def _read_u32(api: _WinAPI, addr: int) -> int:
    data = api.read(addr, 4)
    return struct.unpack("<I", data)[0]


def _write_u32(api: _WinAPI, addr: int, value: int):
    api.write(addr, struct.pack("<I", value & 0xFFFFFFFF))


def _read_string(api: _WinAPI, addr: int, max_len: int = 64) -> str:
    data = api.read(addr, max_len)
    null_pos = data.find(b"\x00")
    if null_pos >= 0:
        data = data[:null_pos]
    return data.decode("ascii", errors="replace")


# ── Main API ─────────────────────────────────────────────────────────────────

class MC3API:
    """Live connection to MC3 game state in PCSX2.

    Usage:
        mc3 = MC3API.connect()
        print(mc3.snapshot())
        mc3.write_u32(0x007D2310, some_value)
        mc3.patch_jal(HOOK_CAREER_LOAD)
    """

    def __init__(self, api: _WinAPI, mailbox_host: int):
        self._api = api
        self._mailbox_host = mailbox_host
        self._ee_base = mailbox_host - ADDR_MAILBOX

    @classmethod
    def connect(cls, timeout: float = 30.0) -> "MC3API":
        """Find PCSX2, locate EE RAM, and return a live API handle."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            pid = _WinAPI.find_pcsx2_pid()
            if pid is not None:
                break
            time.sleep(1)
        else:
            raise RuntimeError("PCSX2 not running")

        api = _WinAPI(pid)
        mb_host = _find_mailbox(api)
        return cls(api, mb_host)

    def close(self):
        self._api.close()

    # ── Core read/write ──────────────────────────────────────────────────

    def read(self, ee_addr: int, size: int) -> bytes:
        return self._api.read(self._ee_base + ee_addr, size)

    def write(self, ee_addr: int, data: bytes):
        return self._api.write(self._ee_base + ee_addr, data)

    def read_u32(self, ee_addr: int) -> int:
        return _read_u32(self._api, self._ee_base + ee_addr)

    def write_u32(self, ee_addr: int, value: int):
        _write_u32(self._api, self._ee_base + ee_addr, value)

    def read_string(self, ee_addr: int, max_len: int = 64) -> str:
        return _read_string(self._api, self._ee_base + ee_addr, max_len)

    # ── Game state ───────────────────────────────────────────────────────

    @property
    def profile_ptr(self) -> int:
        return self.read_u32(ADDR_PROFILE_PTR)

    @property
    def vehicle_list_ptr(self) -> int:
        return self.read_u32(ADDR_VEH_LIST_PTR)

    @property
    def vehicle_count(self) -> int:
        return self.read_u32(ADDR_VEH_COUNT)

    @property
    def vehicles(self) -> List[Vehicle]:
        return _discover_vehicles(self._api, self._ee_base, ADDR_VEH_LIST_PTR)

    @property
    def mailbox_build_id(self) -> int:
        return self.read_u32(ADDR_MAILBOX + 4)

    @property
    def mailbox_heartbeat(self) -> int:
        return self.read_u32(ADDR_MAILBOX + 0x0C)

    def snapshot(self) -> GameSnapshot:
        """Capture all discoverable game state."""
        profile = self.profile_ptr
        prof_data = b""
        if 0x00100000 < profile < 0x02000000:
            try:
                prof_data = self.read(profile, 256)
            except OSError:
                pass

        return GameSnapshot(
            profile_ptr=profile,
            vehicle_list_ptr=self.vehicle_list_ptr,
            vehicle_count=self.vehicle_count,
            vehicles=self.vehicles,
            mailbox_build_id=self.mailbox_build_id,
            mailbox_heartbeat=self.mailbox_heartbeat,
            profile_first_256=prof_data,
        )

    # ── Hook testing ─────────────────────────────────────────────────────

    def patch_jal(self, ee_addr: int, handler_addr: int) -> int:
        """Replace a JAL instruction with a new target. Returns original instruction."""
        orig = self.read_u32(ee_addr)
        op = (orig >> 26) & 0x3F
        if op != 0x03:
            print(f"[WARN] 0x{ee_addr:08X} is not a JAL (opcode={op}) — original=0x{orig:08X}")

        jal = 0x0C000000 | ((handler_addr >> 2) & 0x03FFFFFF)
        self.write_u32(ee_addr, jal)
        return orig

    def restore_jal(self, ee_addr: int, original_instr: int):
        """Restore an original JAL instruction."""
        self.write_u32(ee_addr, original_instr)

    # ── Debug ────────────────────────────────────────────────────────────

    def hexdump(self, ee_addr: int, size: int = 64) -> str:
        """Return a formatted hex dump of EE memory."""
        data = self.read(ee_addr, size)
        lines = []
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            hx = " ".join(f"{b:02X}" for b in chunk)
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"  {ee_addr + i:08X}: {hx:<48s} {asc}")
        return "\n".join(lines)

    def __repr__(self):
        return f"MC3API(ee_base=0x{self._ee_base:016X}, build_id={self.mailbox_build_id})"


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("MC3AP Live API — connecting...")
    mc3 = MC3API.connect(timeout=60)
    print(f"Connected: {mc3}")

    snap = mc3.snapshot()
    print(f"\nProfile ptr: 0x{snap.profile_ptr:08X}")
    print(f"Vehicle list: 0x{snap.vehicle_list_ptr:08X}")
    print(f"Vehicle count: {snap.vehicle_count}")
    print(f"Mailbox build_id: {snap.mailbox_build_id}")
    print(f"Mailbox heartbeat: {snap.mailbox_heartbeat}")

    print(f"\nVehicles ({len(snap.vehicles)} discovered):")
    for v in snap.vehicles[:10]:
        print(f"  [{v.index:2d}] {v.name}")

    if snap.profile_first_256:
        print(f"\nProfile first 256 bytes:")
        print(mc3.hexdump(snap.profile_ptr, 256))

    mc3.close()