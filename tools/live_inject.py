"""MC3AP Live Injector — writes to EE RAM without PCSX2 restart.

Usage:
  python tools/live_inject.py                           # find mailbox + status
  python tools/live_inject.py write 0x0072000C 0x2A     # write dword to EE addr
  python tools/live_inject.py read 0x00720000 64        # read 64 bytes from EE
  python tools/live_inject.py watch 0x0072000C 1        # poll address every 1s
  python tools/live_inject.py patch 0x004AE100 0x00000000 # write to EE (raw word)
  python tools/live_inject.py probe 0x00619B14          # follow pointer chain
"""

import ctypes
import ctypes.wintypes
import struct
import subprocess
import sys
import time
from typing import Optional


# ── Windows API ──────────────────────────────────────────────────────────────
_k32 = ctypes.windll.kernel32

_ReadProcessMemory = _k32.ReadProcessMemory
_ReadProcessMemory.argtypes = [
    ctypes.wintypes.HANDLE, ctypes.wintypes.LPCVOID,
    ctypes.wintypes.LPVOID, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
_ReadProcessMemory.restype = ctypes.wintypes.BOOL

_WriteProcessMemory = _k32.WriteProcessMemory
_WriteProcessMemory.argtypes = [
    ctypes.wintypes.HANDLE, ctypes.wintypes.LPVOID,
    ctypes.wintypes.LPCVOID, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
_WriteProcessMemory.restype = ctypes.wintypes.BOOL


def _e(fn, *a):
    r = fn(*a)
    if not r:
        raise OSError(ctypes.get_last_error())
    return r


# ── Connection ───────────────────────────────────────────────────────────────

def connect() -> tuple:
    """Connect to PCSX2 and find EE RAM. Returns (handle, ee_base_host)."""
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq pcsx2-qt.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True,
    )
    for line in result.stdout.strip().split("\n"):
        parts = line.replace('"', "").split(",")
        if len(parts) >= 2 and "pcsx2-qt.exe" in parts[0]:
            pid = int(parts[1])
            break
    else:
        raise RuntimeError("pcsx2-qt.exe not running")

    h = _k32.OpenProcess(0x0010 | 0x0020 | 0x0008 | 0x0400, False, pid)
    if not h:
        raise RuntimeError(f"Cannot open PID {pid} — run as Administrator")

    # Find EE RAM by searching for mailbox marker
    ee_host = _find_mailbox(h)
    if ee_host is None:
        raise RuntimeError("Mailbox not found — is 60A42FF5.pnach loaded?")

    return h, ee_host, pid


def _find_mailbox(h) -> Optional[int]:
    """Fast scan for 'MC3A' + CRC in large committed regions."""
    class MBI(ctypes.Structure):
        _fields_ = [
            ("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
            ("AllocationProtect", ctypes.wintypes.DWORD), ("PartitionId", ctypes.wintypes.WORD),
            ("RegionSize", ctypes.c_size_t), ("State", ctypes.wintypes.DWORD),
            ("Protect", ctypes.wintypes.DWORD), ("Type", ctypes.wintypes.DWORD),
        ]

    _VirtualQueryEx = _k32.VirtualQueryEx
    _VirtualQueryEx.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPCVOID, ctypes.POINTER(MBI), ctypes.c_size_t]
    _VirtualQueryEx.restype = ctypes.c_size_t

    mbi = MBI()
    addr = ctypes.c_void_p(0)
    marker = b"MC3A"
    crc_bytes = struct.pack("<I", 0x60A42FF5)

    while True:
        r = _VirtualQueryEx(h, addr, ctypes.byref(mbi), ctypes.sizeof(mbi))
        if r == 0: break
        if mbi.State == 0x1000 and mbi.RegionSize >= 1024 * 1024:
            base = mbi.BaseAddress or 0
            buf = ctypes.create_string_buffer(1024 * 1024)
            br = ctypes.c_size_t()
            ok = _ReadProcessMemory(h, ctypes.c_void_p(base), buf, min(mbi.RegionSize, 1024*1024), ctypes.byref(br))
            if ok and br.value >= 16:
                idx = 0
                while True:
                    idx = buf.raw.find(marker, idx)
                    if idx < 0: break
                    if idx + 16 <= br.value and buf.raw[idx+8:idx+12] == crc_bytes:
                        return base + idx
                    idx += 1
        nxt = (mbi.BaseAddress or 0) + mbi.RegionSize
        if nxt <= (addr.value or 0): break
        addr = ctypes.c_void_p(nxt)
    return None


# ── EE RAM helpers ───────────────────────────────────────────────────────────

def ee_to_host(ee_host, ee_addr):
    """Convert EE address to host virtual address."""
    # EE host base is where mailbox (EE 0x00720000) is mapped
    ee_base_ee = 0x00720000
    return ee_host - ee_base_ee + ee_addr


def read_ee(handle, ee_host, ee_addr, size=4):
    """Read bytes from an EE address."""
    host = ee_to_host(ee_host, ee_addr)
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t()
    _e(_ReadProcessMemory, handle, ctypes.c_void_p(host), buf, size, ctypes.byref(br))
    return buf.raw[:br.value]


def read_dword(handle, ee_host, ee_addr):
    return struct.unpack("<I", read_ee(handle, ee_host, ee_addr, 4))[0]


def write_ee(handle, ee_host, ee_addr, data: bytes):
    """Write bytes to an EE address."""
    host = ee_to_host(ee_host, ee_addr)
    buf = ctypes.create_string_buffer(data)
    bw = ctypes.c_size_t()
    _e(_WriteProcessMemory, handle, ctypes.c_void_p(host), buf, len(data), ctypes.byref(bw))
    return bw.value


def write_dword(handle, ee_host, ee_addr, value: int):
    return write_ee(handle, ee_host, ee_addr, struct.pack("<I", value & 0xFFFFFFFF))


# ── High-level tools ─────────────────────────────────────────────────────────

def probe_pointer(handle, ee_host, ee_addr, depth=3):
    """Follow pointer chains and show results."""
    seen = set()
    addr = ee_addr
    for i in range(depth):
        try:
            val = read_dword(handle, ee_host, addr)
        except OSError:
            print(f"  [{i}] 0x{addr:08X} -> (unreadable)")
            break
        label = ""
        if addr == 0x00619B14: label = " [Profile Ptr]"
        elif addr == 0x006E0170: label = " [Vehicle List Ptr]"
        elif addr == 0x006E0174: label = " [Vehicle Count]"
        print(f"  [{i}] 0x{addr:08X} -> 0x{val:08X}{label}")
        if val == 0 or val < 0x00100000 or val > 0x02000000 or val in seen:
            break
        seen.add(val)
        addr = val


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_status(handle, ee_host):
    mb = read_ee(handle, ee_host, 0x00720000, 64)
    print(f"PCSX2 PID: {pid}")
    print(f"EE host base: 0x{ee_host:016X}")
    print(f"Mailbox:")
    for i in range(0, 64, 16):
        hex_str = " ".join(f"{b:02X}" for b in mb[i:i+16])
        print(f"  0x0072{i:04X}: {hex_str}")
    print(f"  build_id={struct.unpack_from('<I', mb, 4)[0]}")
    print(f"  crc=0x{struct.unpack_from('<I', mb, 8)[0]:08X}")
    print(f"  hb={struct.unpack_from('<I', mb, 12)[0]}")

    # Show known game pointers
    print(f"\nGame pointers:")
    probe_pointer(handle, ee_host, 0x00619B14)  # profile
    probe_pointer(handle, ee_host, 0x006E0170)  # vehicle list


def cmd_write(handle, ee_host, addr_str, value_str):
    addr = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)
    value = int(value_str, 16) if value_str.startswith("0x") else int(value_str)
    write_dword(handle, ee_host, addr, value)
    verify = read_dword(handle, ee_host, addr)
    print(f"EE 0x{addr:08X}: wrote 0x{value:08X}, read 0x{verify:08X} {'[OK]' if verify == value else '[MISMATCH]'}")


def cmd_read(handle, ee_host, addr_str, size=64):
    addr = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)
    size = int(size)
    data = read_ee(handle, ee_host, addr, size)
    for i in range(0, len(data), 16):
        hex_str = " ".join(f"{b:02X}" for b in data[i:i+16])
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in data[i:i+16])
        print(f"  0x{addr+i:08X}: {hex_str:<48s} {ascii_str}")


def cmd_watch(handle, ee_host, addr_str, interval=1.0):
    addr = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)
    interval = float(interval)
    try:
        while True:
            val = read_dword(handle, ee_host, addr)
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] 0x{addr:08X} = 0x{val:08X} ({val})")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Stopped.")


def cmd_patch(handle, ee_host, addr_str, value_str):
    """Write a raw word to a specific EE address (for hook patching)."""
    addr = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)
    value = int(value_str, 16) if value_str.startswith("0x") else int(value_str)

    # Read current value first
    old = read_dword(handle, ee_host, addr)
    print(f"EE 0x{addr:08X}: old=0x{old:08X}")

    # Write new value
    write_dword(handle, ee_host, addr, value)
    verify = read_dword(handle, ee_host, addr)
    print(f"                new=0x{verify:08X} {'[OK]' if verify == value else '[MISMATCH]'}")

    # Interpret if it's a MIPS instruction
    op = (value >> 26) & 0x3F
    if op == 0x03:
        target = (value & 0x03FFFFFF) << 2
        print(f"                JAL 0x{target:08X}")
    elif op == 0x02:
        target = (value & 0x03FFFFFF) << 2
        print(f"                J 0x{target:08X}")
    elif value == 0:
        print(f"                NOP")


def cmd_hexpatch(handle, ee_host, addr_str, *words):
    """Write multiple words starting at an EE address."""
    addr = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)
    for i, w in enumerate(words):
        val = int(w, 16) if w.startswith("0x") else int(w)
        write_dword(handle, ee_host, addr + i * 4, val)
    print(f"Wrote {len(words)} words to 0x{addr:08X}")


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "find":
        pid = None
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq pcsx2-qt.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True,
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.replace('"', "").split(",")
            if len(parts) >= 2 and "pcsx2-qt.exe" in parts[0]:
                pid = int(parts[1])
                break
        if pid:
            print(f"PID={pid}")
        else:
            print("PCSX2 not running")

    else:
        h, ee_host, pid = connect()

        if cmd == "status":
            cmd_status(h, ee_host)
        elif cmd == "write" and len(args) >= 2:
            cmd_write(h, ee_host, args[0], args[1])
        elif cmd == "read" and len(args) >= 1:
            cmd_read(h, ee_host, args[0], args[1] if len(args) >= 2 else 64)
        elif cmd == "watch" and len(args) >= 1:
            cmd_watch(h, ee_host, args[0], args[1] if len(args) >= 2 else 1.0)
        elif cmd == "patch" and len(args) >= 2:
            cmd_patch(h, ee_host, args[0], args[1])
        elif cmd == "probe" and len(args) >= 1:
            addr = int(args[0], 16) if args[0].startswith("0x") else int(args[0])
            probe_pointer(handle, ee_host, addr)
        elif cmd == "hexpatch" and len(args) >= 2:
            cmd_hexpatch(h, ee_host, args[0], *args[1:])
        else:
            print(f"Unknown command: {cmd}")
            print(__doc__)

        _k32.CloseHandle(h)