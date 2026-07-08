"""Exploration Harness — automated memory diff and hook probe for MC3.

Loads a savestate → snapshots memory → sends input → snapshots again → diffs.
Finds game values by observing what changes between states.

Usage:
    python tools/run_explore.py 1              # explore save state 1 (post-tutorial)
    python tools/run_explore.py 2              # explore save state 2 (vanessa prompt)
    python tools/run_explore.py diff 1 5       # diff state 1 vs state 5 (pre vs post vanessa)
    python tools/run_explore.py hook 4         # probe race-finish hook on state 4
"""

import ctypes
import ctypes.wintypes
import json
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ── Paths ────────────────────────────────────────────────────────────────────
PCSX2_EXE = r"E:\Emulator\PCSX2\pcsx2-qt.exe"
ISO_PATH  = r"E:\Emulator\PCSX2\ps2games\MC3.iso"
PNACH_SRC = r"E:\Emulator\PCSX2\cheats\60A42FF5.pnach"
PROJECT   = Path(r"C:\Users\jkpri\mc3-ap")

# ── Windows API ──────────────────────────────────────────────────────────────
_k32 = ctypes.windll.kernel32


class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", ctypes.wintypes.DWORD),
        ("PartitionId", ctypes.wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.wintypes.DWORD),
        ("Protect", ctypes.wintypes.DWORD),
        ("Type", ctypes.wintypes.DWORD),
    ]


class LiveConnection:
    """Live PCSX2 connection for exploration."""

    def __init__(self):
        pid = self._find_pid()
        self._h = _k32.OpenProcess(0x0010 | 0x0020 | 0x0400, False, pid)
        self._mb_host = self._scan_mailbox()
        self._ee_base = self._mb_host - 0x00720000

    def close(self):
        if self._h:
            _k32.CloseHandle(self._h)

    @staticmethod
    def _find_pid():
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq pcsx2-qt.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True,
        )
        for line in r.stdout.strip().split("\n"):
            parts = line.replace('"', "").split(",")
            if len(parts) >= 2 and "pcsx2-qt.exe" in parts[0]:
                return int(parts[1])
        raise RuntimeError("PCSX2 not running")

    def _scan_mailbox(self):
        VQE = _k32.VirtualQueryEx
        VQE.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPCVOID, ctypes.POINTER(MBI), ctypes.c_size_t]
        VQE.restype = ctypes.c_size_t

        RPM = _k32.ReadProcessMemory
        RPM.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPCVOID, ctypes.wintypes.LPVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        RPM.restype = ctypes.wintypes.BOOL

        mbi = MBI(); addr = ctypes.c_void_p(0)
        marker = b"MC3A"; crc = struct.pack("<I", 0x60A42FF5)
        buf = ctypes.create_string_buffer(256*1024); br = ctypes.c_size_t()

        while True:
            r = VQE(self._h, addr, ctypes.byref(mbi), ctypes.sizeof(mbi))
            if r == 0: break
            if mbi.State == 0x1000 and mbi.RegionSize >= 4096:
                base = mbi.BaseAddress or 0
                for off in range(0, min(mbi.RegionSize, 10*1024*1024), len(buf)):
                    ok = RPM(self._h, ctypes.c_void_p(base+off), buf, min(len(buf), mbi.RegionSize-off), ctypes.byref(br))
                    if not ok or br.value < 16: break
                    idx = 0
                    while True:
                        idx = buf.raw.find(marker, idx)
                        if idx < 0: break
                        if idx+12 <= br.value and buf.raw[idx+8:idx+12] == crc:
                            return base + off + idx
                        idx += 1
            nxt = (mbi.BaseAddress or 0) + mbi.RegionSize
            if nxt <= (addr.value or 0): break
            addr = ctypes.c_void_p(nxt)
        raise RuntimeError("Mailbox not found")

    def read(self, ee_addr: int, size: int) -> bytes:
        host = self._ee_base + ee_addr
        buf = ctypes.create_string_buffer(size)
        br = ctypes.c_size_t()
        _k32.ReadProcessMemory(self._h, ctypes.c_void_p(host), buf, size, ctypes.byref(br))
        return buf.raw[:br.value]

    def read_u32(self, ee_addr: int) -> int:
        return struct.unpack("<I", self.read(ee_addr, 4))[0]

    def read_string(self, ee_addr: int, max_len=64) -> str:
        data = self.read(ee_addr, max_len)
        null = data.find(b"\x00")
        return data[:null].decode("ascii", errors="replace") if null >= 0 else data.decode("ascii", errors="replace")

    def write_u32(self, ee_addr: int, value: int):
        host = self._ee_base + ee_addr
        data = struct.pack("<I", value & 0xFFFFFFFF)
        bw = ctypes.c_size_t()
        _k32.WriteProcessMemory(self._h, ctypes.c_void_p(host), data, 4, ctypes.byref(bw))

    def snapshot_region(self, ee_start: int, ee_size: int) -> bytes:
        """Read a full region for diffing."""
        return self.read(ee_start, ee_size)

    def heartbeat(self) -> int:
        return self.read_u32(0x0072000C)

    def mailbox_build(self) -> int:
        return self.read_u32(0x00720004)


# ── Memory regions to snapshot ───────────────────────────────────────────────

# Key regions that change during gameplay
MONITOR_REGIONS = [
    # name, ee_start, size, description
    ("profile_ptr_area", 0x00619B00, 0x100, "Profile pointer + nearby globals"),
    ("profile_data",     None,        0x800,  "Profile struct at pProfile"),
    ("vehicle_list",     0x007D28B0,  0x2000, "Vehicle array (94 * ~0x54)"),
    ("event_area",       0x007D4000,  0x4000, "Possible event/race state area"),
    ("mailbox",          0x00720000,  0x400,  "MC3AP mailbox + game string area"),
    ("globals",          0x006E0000,  0x200,  "Global pointers (veh list, count)"),
]


# ── Snapshot ─────────────────────────────────────────────────────────────────

@dataclass
class MemorySnapshot:
    state_label: str
    timestamp: float
    mailbox_build: int
    heartbeat: int
    regions: Dict[str, bytes]  # region_name -> raw bytes
    profile_ptr: int
    vehicle_list_ptr: int

    def to_dict(self) -> dict:
        """Serializable subset."""
        return {
            "state_label": self.state_label,
            "timestamp": self.timestamp,
            "mailbox_build": self.mailbox_build,
            "heartbeat": self.heartbeat,
            "profile_ptr": self.profile_ptr,
            "vehicle_list_ptr": self.vehicle_list_ptr,
            "region_sizes": {k: len(v) for k, v in self.regions.items()},
        }

    def save(self, path: str):
        data = {
            "meta": self.to_dict(),
            "regions": {k: v.hex() for k, v in self.regions.items()},
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


# ── Diff ─────────────────────────────────────────────────────────────────────

@dataclass
class MemoryChange:
    ee_addr: int
    offset_in_region: int
    region: str
    old_bytes: bytes
    new_bytes: bytes

    @property
    def old_u32(self): return struct.unpack("<I", self.old_bytes)[0] if len(self.old_bytes) >= 4 else 0
    @property
    def new_u32(self): return struct.unpack("<I", self.new_bytes)[0] if len(self.new_bytes) >= 4 else 0

    def __repr__(self):
        return (f"0x{self.ee_addr:08X} [{self.region}] "
                f"0x{self.old_u32:08X} -> 0x{self.new_u32:08X} "
                f"({self.old_u32} -> {self.new_u32})")


def diff_snapshots(before: MemorySnapshot, after: MemorySnapshot,
                   min_change=1, max_changes=200) -> List[MemoryChange]:
    """Compare two snapshots, return changed dwords."""
    changes = []
    for name in before.regions:
        if name not in after.regions:
            continue
        ba = before.regions[name]
        bb = after.regions[name]
        if len(ba) != len(bb):
            continue

        # For profile_data, the EE base comes from the snapshot
        if name == "profile_data":
            ee_base = before.profile_ptr
        elif name == "profile_ptr_area":
            ee_base = 0x00619B00
        elif name == "vehicle_list":
            ee_base = 0x007D28B0
        elif name == "event_area":
            ee_base = 0x007D4000
        elif name == "mailbox":
            ee_base = 0x00720000
        elif name == "globals":
            ee_base = 0x006E0000
        else:
            ee_base = 0

        for off in range(0, len(ba), 4):
            if ba[off:off+4] != bb[off:off+4]:
                changes.append(MemoryChange(
                    ee_addr=ee_base + off,
                    offset_in_region=off,
                    region=name,
                    old_bytes=ba[off:off+4],
                    new_bytes=bb[off:off+4],
                ))
                if len(changes) >= max_changes:
                    break
        if len(changes) >= max_changes:
            break
    return changes


# ── Snapshot capture ─────────────────────────────────────────────────────────

def capture_snapshot(mc3: LiveConnection, label: str,
                     extra_regions: Optional[List[Tuple[str, int, int]]] = None
                     ) -> MemorySnapshot:
    """Capture all monitor regions from the live game."""
    regions = {}

    for name, start, size, _desc in MONITOR_REGIONS:
        actual_start = start
        if name == "profile_data":
            actual_start = mc3.read_u32(0x00619B14)
            if not (0x00100000 < actual_start < 0x02000000):
                actual_start = 0x007D2310  # fallback
        try:
            regions[name] = mc3.snapshot_region(actual_start, min(size, 0x1000))
        except OSError:
            regions[name] = b""

    if extra_regions:
        for name, start, size in extra_regions:
            try:
                regions[name] = mc3.snapshot_region(start, size)
            except OSError:
                regions[name] = b""

    return MemorySnapshot(
        state_label=label,
        timestamp=time.time(),
        mailbox_build=mc3.mailbox_build(),
        heartbeat=mc3.heartbeat(),
        regions=regions,
        profile_ptr=mc3.read_u32(0x00619B14),
        vehicle_list_ptr=mc3.read_u32(0x006E0170),
    )


# ── Hook probing ─────────────────────────────────────────────────────────────

def inject_probe_hook(mc3: LiveConnection, hook_addr: int, handler_addr: int,
                      original_jal: int) -> int:
    """Install a JAL hook temporarily, return original instruction."""
    mc3.write_u32(hook_addr, 0x0C000000 | ((handler_addr >> 2) & 0x03FFFFFF))
    return original_jal


def read_probe_event(mc3: LiveConnection, probe_ee: int = 0x00720200) -> dict:
    """Read a raw ProbeEvent from the mailbox debug area."""
    data = mc3.read(probe_ee, 48)
    return {
        "hook_id":   struct.unpack_from("<I", data, 0)[0],
        "count":     struct.unpack_from("<I", data, 4)[0],
        "pc":        f"0x{struct.unpack_from('<I', data, 8)[0]:08X}",
        "ra":        f"0x{struct.unpack_from('<I', data, 12)[0]:08X}",
        "sp":        f"0x{struct.unpack_from('<I', data, 16)[0]:08X}",
        "a0":        f"0x{struct.unpack_from('<I', data, 20)[0]:08X}",
        "a1":        f"0x{struct.unpack_from('<I', data, 24)[0]:08X}",
        "a2":        f"0x{struct.unpack_from('<I', data, 28)[0]:08X}",
        "a3":        f"0x{struct.unpack_from('<I', data, 32)[0]:08X}",
        "v0":        f"0x{struct.unpack_from('<I', data, 36)[0]:08X}",
        "v1":        f"0x{struct.unpack_from('<I', data, 40)[0]:08X}",
        "sample_0":  f"0x{struct.unpack_from('<I', data, 44)[0]:08X}",
    }


# ── Vehicle scan ─────────────────────────────────────────────────────────────

def scan_vehicles(mc3: LiveConnection) -> List[dict]:
    """Scan for vehicles with candidate stride sizes."""
    vl = mc3.read_u32(0x006E0170)
    results = []
    for stride in [0x50, 0x54, 0x58, 0x60, 0x68, 0x70]:
        count = 0
        vehicles = []
        for i in range(100):
            addr = vl + i * stride
            name_ptr = mc3.read_u32(addr)
            if not (0x00500000 < name_ptr < 0x01000000):
                if i >= 2: break
                continue
            try:
                name = mc3.read_string(name_ptr, 32)
            except:
                break
            if name and len(name) > 2 and "vp_" in name.lower() or "chopper" in name.lower() or "bike" in name.lower():
                count += 1
                vehicles.append({"index": i, "name": name, "addr": f"0x{addr:08X}"})
        if count > 5:
            results.append({"stride": stride, "count": count, "vehicles": vehicles[:5]})
    return results


# ── CLI ──────────────────────────────────────────────────────────────────────

def cmd_boot(state: int):
    """Boot PCSX2 with a specific save state."""
    # Kill existing
    subprocess.run(["taskkill", "/F", "/IM", "pcsx2-qt.exe"],
                   capture_output=True)
    time.sleep(1)

    print(f"Booting PCSX2 with save state {state}...")
    subprocess.Popen(
        [PCSX2_EXE, "-fastboot", "-state", str(state), ISO_PATH],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(20)

    # Verify
    try:
        mc3 = LiveConnection()
        print(f"  Connected: build_id={mc3.mailbox_build()} HB={mc3.heartbeat()}")
        mc3.close()
        print("  [OK] PCSX2 booted, mailbox found")
    except RuntimeError as e:
        print(f"  [FAIL] {e}")


def cmd_snapshot(state_label: str, output_path: str):
    """Capture a full memory snapshot."""
    mc3 = LiveConnection()
    snap = capture_snapshot(mc3, state_label)
    snap.save(output_path)
    print(f"Snapshot saved: {output_path}")
    print(f"  profile=0x{snap.profile_ptr:08X} veh_list=0x{snap.vehicle_list_ptr:08X}")
    print(f"  HB={snap.heartbeat} build={snap.mailbox_build}")
    mc3.close()


def cmd_diff(state_a: str, state_b: str):
    """Diff two snapshots."""
    import json
    with open(state_a) as f: a = json.load(f)
    with open(state_b) as f: b = json.load(f)

    # Reconstruct snapshots
    regions_a = {}
    regions_b = {}
    for k in a["regions"]:
        regions_a[k] = bytes.fromhex(a["regions"][k])
    for k in b["regions"]:
        regions_b[k] = bytes.fromhex(b["regions"][k])

    before = MemorySnapshot(
        state_label=a["meta"]["state_label"],
        timestamp=a["meta"]["timestamp"],
        mailbox_build=a["meta"]["mailbox_build"],
        heartbeat=a["meta"]["heartbeat"],
        regions=regions_a,
        profile_ptr=a["meta"]["profile_ptr"],
        vehicle_list_ptr=a["meta"]["vehicle_list_ptr"],
    )
    after = MemorySnapshot(
        state_label=b["meta"]["state_label"],
        timestamp=b["meta"]["timestamp"],
        mailbox_build=b["meta"]["mailbox_build"],
        heartbeat=b["meta"]["heartbeat"],
        regions=regions_b,
        profile_ptr=b["meta"]["profile_ptr"],
        vehicle_list_ptr=b["meta"]["vehicle_list_ptr"],
    )

    changes = diff_snapshots(before, after)
    print(f"Diff: {state_a} -> {state_b}")
    print(f"Changes: {len(changes)}")
    for ch in changes:
        print(f"  {ch}")


def cmd_vehicles():
    """Scan vehicle array."""
    mc3 = LiveConnection()
    results = scan_vehicles(mc3)
    print("Vehicle array scan:")
    for r in results:
        print(f"  stride=0x{r['stride']:02X} ({r['stride']}): {r['count']} vehicles")
        for v in r["vehicles"]:
            print(f"    [{v['index']:2d}] {v['name']}")
    mc3.close()


def cmd_explore(state: int):
    """Full exploration of a save state."""
    print(f"=== Exploring Save State {state} ===")

    # Ensure booted
    try:
        mc3 = LiveConnection()
    except RuntimeError:
        print("PCSX2 not running. Boot with: python run_explore.py boot N")
        return

    snap = capture_snapshot(mc3, f"state_{state}")

    # 1. Basic info
    print(f"\n--- Snapshot Info ---")
    print(f"Profile ptr: 0x{snap.profile_ptr:08X}")
    print(f"Vehicle list: 0x{snap.vehicle_list_ptr:08X}")
    print(f"HB: {snap.heartbeat}  Build: {snap.mailbox_build}")

    # 2. Vehicle scan
    print(f"\n--- Vehicle Array ---")
    for r in scan_vehicles(mc3):
        print(f"  stride=0x{r['stride']:02X}: {r['count']} vehicles")
        for v in r["vehicles"]:
            print(f"    [{v['index']:2d}] {v['name']}")

    # 3. Profile exploration
    print(f"\n--- Profile at 0x{snap.profile_ptr:08X} ---")
    prof = snap.regions.get("profile_data", b"")
    if prof:
        print(f"  Size: {len(prof)} bytes")
        print(f"  First 64 bytes:")
        for i in range(0, min(64, len(prof)), 16):
            hx = " ".join(f"{b:02X}" for b in prof[i:i+16])
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in prof[i:i+16])
            print(f"    +{i:03X}: {hx}  {asc}")

        # Scan for money-like values (500-50000, not powers of 2)
        print(f"\n  Candidate money values (non-power-of-2, 500-50000):")
        for off in range(0, len(prof), 4):
            val = struct.unpack_from("<I", prof, off)[0]
            if 500 <= val <= 50000:
                # Skip powers of 2
                if val & (val - 1) != 0:
                    print(f"    +{off:03X}: {val:>8d} (0x{val:08X})")

    # 4. Mailbox area — look for game strings
    print(f"\n--- Mailbox Area Strings ---")
    mb = snap.regions.get("mailbox", b"")
    if mb:
        # Find ASCII strings >= 4 chars
        for i in range(0, min(len(mb) - 4, 512), 1):
            if 32 <= mb[i] < 127 and 32 <= mb[i+1] < 127 and 32 <= mb[i+2] < 127 and 32 <= mb[i+3] < 127:
                end = i
                while end < len(mb) and 32 <= mb[end] < 127:
                    end += 1
                s = mb[i:end].decode("ascii")
                if len(s) >= 6 and "CDCD" not in s:
                    print(f"  0x{0x00720000+i:08X}: {s}")
                    # skip past this string
                    i = end

    # Save snapshot
    out = str(PROJECT / f"snapshot_state{state}.json")
    snap.save(out)
    print(f"\nSnapshot saved: {out}")

    mc3.close()


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "boot" and args:
        cmd_boot(int(args[0]))
    elif cmd == "snapshot" and len(args) >= 2:
        cmd_snapshot(args[0], args[1])
    elif cmd == "diff" and len(args) >= 2:
        cmd_diff(args[0], args[1])
    elif cmd == "vehicles":
        cmd_vehicles()
    elif cmd == "explore" and args:
        cmd_explore(int(args[0]))
    else:
        # Default: explore a state by number
        try:
            state_num = int(cmd)
            cmd_explore(state_num)
        except ValueError:
            print(f"Unknown command: {cmd}")
            print(__doc__)