"""PCSX2 EE RAM mailbox bridge — discovers, reads, and writes the MC3AP mailbox.

Usage:
  python tools/probe_memory.py              # one-shot discovery + status
  python tools/probe_memory.py --watch      # poll heartbeat every 1s
  python tools/probe_memory.py --write KEY=VALUE  # write a field
"""

import ctypes
import ctypes.wintypes
import struct
import sys
import subprocess
import time
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Windows API wrappers
# ---------------------------------------------------------------------------

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress",       ctypes.c_void_p),
        ("AllocationBase",    ctypes.c_void_p),
        ("AllocationProtect", ctypes.wintypes.DWORD),
        ("PartitionId",       ctypes.wintypes.WORD),
        ("RegionSize",        ctypes.c_size_t),
        ("State",             ctypes.wintypes.DWORD),
        ("Protect",           ctypes.wintypes.DWORD),
        ("Type",              ctypes.wintypes.DWORD),
    ]


_k32 = ctypes.windll.kernel32

MEM_COMMIT  = 0x1000
VM_READ     = 0x0010
VM_WRITE    = 0x0020
VM_OPERATION = 0x0008
QUERY_INFO  = 0x0400
DESIRED     = VM_READ | VM_WRITE | VM_OPERATION | QUERY_INFO


def _e(fn, *a, **kw):
    """Call a kernel32 function, raise OSError on failure."""
    r = fn(*a, **kw)
    if not r and fn != _k32.CloseHandle:
        raise OSError(ctypes.get_last_error())
    return r


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

_VirtualQueryEx = _k32.VirtualQueryEx
_VirtualQueryEx.argtypes = [
    ctypes.wintypes.HANDLE, ctypes.wintypes.LPCVOID,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t,
]
_VirtualQueryEx.restype = ctypes.c_size_t


# ---------------------------------------------------------------------------
# Mailbox layout (must match payload/include/mailbox.h)
# ---------------------------------------------------------------------------

@dataclass
class MailboxHeader:
    """First 64 bytes of the MC3AP mailbox, as seen via PNACH boot write."""
    magic:      bytes        # 4 bytes — "MC3A"
    build_id:   int          # u32 at +0x04
    game_crc:   int          # u32 at +0x08
    heartbeat:  int          # u32 at +0x0C — game increments
    hb_python:  int          # u32 at +0x10 — Python increments

    host_addr:  int = 0      # host virtual address where magic was found
    ee_addr:    int = 0x00720000


MAILBOX_MAGIC = b"MC3A"
EXPECTED_CRC = 0x60A42FF5
EXPECTED_BUILD = 9


# ---------------------------------------------------------------------------
# Process discovery
# ---------------------------------------------------------------------------

def _find_pcsx2_pid() -> Optional[int]:
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


def _open_process(pid: int):
    h = _k32.OpenProcess(DESIRED, False, pid)
    if not h:
        raise OSError(f"Cannot open PID {pid} — run as Administrator?")
    return h


# ---------------------------------------------------------------------------
# Mailbox discovery
# ---------------------------------------------------------------------------

def find_mailbox(handle) -> Optional[MailboxHeader]:
    """Scan PCSX2 committed memory for the mailbox.

    Searches for the pattern: MC3A + build_id(1) + CRC(0x60A42FF5)
    within large committed memory regions.
    """
    mbi = MEMORY_BASIC_INFORMATION()
    addr = ctypes.c_void_p(0)
    chunk = 256 * 1024
    buf = ctypes.create_string_buffer(chunk)
    br = ctypes.c_size_t()

    while True:
        result = _VirtualQueryEx(handle, addr, ctypes.byref(mbi), ctypes.sizeof(mbi))
        if result == 0:
            break

        if mbi.State == MEM_COMMIT and mbi.RegionSize >= 4096:
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize

            for offset in range(0, min(size, 150 * 1024 * 1024), chunk):
                ok = _ReadProcessMemory(handle, ctypes.c_void_p(base + offset), buf, chunk, ctypes.byref(br))
                if not ok or br.value < 16:
                    break

                data = buf.raw[:br.value]
                idx = 0
                while True:
                    idx = data.find(MAILBOX_MAGIC, idx)
                    if idx < 0:
                        break
                    if idx + 16 <= len(data):
                        bid = struct.unpack_from("<I", data, idx + 4)[0]
                        crc = struct.unpack_from("<I", data, idx + 8)[0]
                        hb  = struct.unpack_from("<I", data, idx + 12)[0]
                        if bid == EXPECTED_BUILD and crc == EXPECTED_CRC:
                            host = base + offset + idx
                            hb_py = struct.unpack_from("<I", data, idx + 16)[0] if idx + 20 <= len(data) else 0
                            return MailboxHeader(
                                magic=MAILBOX_MAGIC, build_id=bid, game_crc=crc,
                                heartbeat=hb, hb_python=hb_py,
                                host_addr=host,
                            )
                    idx += 1

        nxt = (mbi.BaseAddress or 0) + mbi.RegionSize
        if nxt <= (addr.value or 0):
            break
        addr = ctypes.c_void_p(nxt)

    return None


# ---------------------------------------------------------------------------
# Read / Write helpers
# ---------------------------------------------------------------------------

def read_mailbox(handle, mb: MailboxHeader) -> MailboxHeader:
    """Re-read current values from the live mailbox."""
    buf = ctypes.create_string_buffer(64)
    br = ctypes.c_size_t()
    _e(_ReadProcessMemory, handle, ctypes.c_void_p(mb.host_addr), buf, 64, ctypes.byref(br))
    raw = buf.raw
    return MailboxHeader(
        magic=MAILBOX_MAGIC,
        build_id=struct.unpack_from("<I", raw, 4)[0],
        game_crc=struct.unpack_from("<I", raw, 8)[0],
        heartbeat=struct.unpack_from("<I", raw, 12)[0],
        hb_python=struct.unpack_from("<I", raw, 16)[0],
        host_addr=mb.host_addr,
        ee_addr=mb.ee_addr,
    )


def write_heartbeat_python(handle, mb: MailboxHeader, value: int):
    """Write heartbeat_python field (offset +0x10)."""
    addr = mb.host_addr + 0x10
    data = struct.pack("<I", value & 0xFFFFFFFF)
    bw = ctypes.c_size_t()
    _e(_WriteProcessMemory, handle, ctypes.c_void_p(addr), data, 4, ctypes.byref(bw))


def read_dword(handle, host_addr: int) -> int:
    buf = ctypes.create_string_buffer(4)
    br = ctypes.c_size_t()
    _e(_ReadProcessMemory, handle, ctypes.c_void_p(host_addr), buf, 4, ctypes.byref(br))
    return struct.unpack("<I", buf.raw[:4])[0]


def write_dword(handle, host_addr: int, value: int):
    data = struct.pack("<I", value & 0xFFFFFFFF)
    bw = ctypes.c_size_t()
    _e(_WriteProcessMemory, handle, ctypes.c_void_p(host_addr), data, 4, ctypes.byref(bw))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_status():
    """One-shot: discover mailbox and show status."""
    pid = _find_pcsx2_pid()
    if pid is None:
        print("[FAIL] pcsx2-qt.exe not running")
        sys.exit(1)

    handle = _open_process(pid)
    try:
        mb = find_mailbox(handle)
        if mb is None:
            print("[FAIL] Mailbox not found — is 60A42FF5.pnach loaded and cheats enabled?")
            sys.exit(1)

        # Re-read live values
        mb = read_mailbox(handle, mb)

        print(f"PCSX2 PID:   {pid}")
        print(f"Host addr:   0x{mb.host_addr:016X}")
        print(f"EE addr:     0x{mb.ee_addr:08X}")
        print(f"Magic:       {mb.magic.decode()}")
        print(f"Build ID:    {mb.build_id}")
        print(f"Game CRC:    0x{mb.game_crc:08X} {'(match)' if mb.game_crc == EXPECTED_CRC else '(MISMATCH!)'}")
        print(f"Heartbeat G: {mb.heartbeat}")
        print(f"Heartbeat P: {mb.hb_python}")

        # Write test: bump heartbeat_python
        new_val = (mb.hb_python + 1) & 0xFFFFFFFF
        write_heartbeat_python(handle, mb, new_val)
        verify = read_dword(handle, mb.host_addr + 0x10)
        if verify == new_val:
            print(f"Write test:  [OK] ({mb.hb_python} -> {new_val}, verified)")
        else:
            print(f"Write test:  [FAIL] wrote {new_val}, read {verify}")

        # Hook check
        if mb.heartbeat > 0:
            print(f"Hook check:  [OK] heartbeat_game = {mb.heartbeat} — hook has fired!")
        else:
            print(f"Hook check:  [PENDING] load a career save to test hook fire")

        return mb

    finally:
        _k32.CloseHandle(handle)


def cmd_watch(interval: float = 1.0):
    """Poll heartbeat every `interval` seconds and print changes."""
    pid = _find_pcsx2_pid()
    if pid is None:
        print("[FAIL] pcsx2-qt.exe not running")
        sys.exit(1)

    handle = _open_process(pid)
    try:
        mb = find_mailbox(handle)
        if mb is None:
            print("[FAIL] Mailbox not found")
            sys.exit(1)

        last_hb = read_dword(handle, mb.host_addr + 0x0C)
        print(f"Watching heartbeat_game (current: {last_hb})… Ctrl+C to stop")
        print(f"{'Time':>8s}  {'hb_game':>8s}  {'delta':>6s}  note")

        while True:
            time.sleep(interval)
            hb = read_dword(handle, mb.host_addr + 0x0C)
            delta = hb - last_hb
            note = ""
            if delta > 0:
                note = "  <-- HOOK FIRED"
            ts = time.strftime("%H:%M:%S")
            print(f"{ts:>8s}  {hb:>8d}  {delta:>+6d}{note}")
            last_hb = hb

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        _k32.CloseHandle(handle)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--watch" in sys.argv:
        interval = 1.0
        try:
            idx = sys.argv.index("--watch")
            if idx + 1 < len(sys.argv):
                interval = float(sys.argv[idx + 1])
        except (ValueError, IndexError):
            pass
        cmd_watch(interval)
    else:
        cmd_status()