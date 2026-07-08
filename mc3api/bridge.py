"""Process-memory bridge to a running stock PCSX2 instance (Windows).

Locates the emulated EE RAM inside the PCSX2 process by scanning for the
MC3AP mailbox marker installed by the PNACH payload, then provides
read/write primitives addressed in EE space.
"""

from __future__ import annotations

import ctypes
import struct
import subprocess
import sys
import time
from typing import Optional

from .memmap import MAP, GAME_CRC

# The bridge drives the Win32 process-memory API. Importing this module must
# still succeed on non-Windows (so the pure-logic package and its tests import
# cleanly in CI); connect() raises a clear error off-Windows instead.
_WINDOWS = sys.platform == "win32"


class BridgeError(RuntimeError):
    pass


if _WINDOWS:
    import ctypes.wintypes

    class _MBI(ctypes.Structure):
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
else:  # pragma: no cover - non-Windows import shim
    _MBI = None


_MEM_COMMIT = 0x1000
_ACCESS = 0x0010 | 0x0020 | 0x0008 | 0x0400  # VM_READ | VM_WRITE | VM_OPERATION | QUERY


class PCSX2Bridge:
    """Read/write EE RAM of a running PCSX2 process.

    All public addresses are EE-space (0x00000000..0x02000000); the host
    base is resolved once at connect time via mailbox scan.
    """

    def __init__(self, pid: int, ee_base_host: int):
        if not _WINDOWS:
            raise BridgeError("PCSX2Bridge requires Windows (Win32 process-memory API)")
        self.pid = pid
        self._ee_base = ee_base_host
        self._k32 = ctypes.windll.kernel32
        self._h = self._k32.OpenProcess(_ACCESS, False, pid)
        if not self._h:
            raise BridgeError(f"Cannot open PCSX2 process {pid} (try running as Administrator)")
        self._rpm = self._k32.ReadProcessMemory
        self._rpm.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPCVOID,
                              ctypes.wintypes.LPVOID, ctypes.c_size_t,
                              ctypes.POINTER(ctypes.c_size_t)]
        self._rpm.restype = ctypes.wintypes.BOOL
        self._wpm = self._k32.WriteProcessMemory
        self._wpm.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPVOID,
                              ctypes.wintypes.LPCVOID, ctypes.c_size_t,
                              ctypes.POINTER(ctypes.c_size_t)]
        self._wpm.restype = ctypes.wintypes.BOOL

    # ── Connection ───────────────────────────────────────────────────────

    @staticmethod
    def find_pid() -> Optional[int]:
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

    @classmethod
    def connect(cls, timeout: float = 30.0) -> "PCSX2Bridge":
        """Find PCSX2, locate EE RAM via mailbox scan, return live bridge."""
        deadline = time.time() + timeout
        pid = None
        while time.time() < deadline:
            pid = cls.find_pid()
            if pid is not None:
                break
            time.sleep(1)
        if pid is None:
            raise BridgeError("PCSX2 (pcsx2-qt.exe) is not running")

        scanner = cls(pid, 0)
        try:
            mailbox_host = scanner._scan_for_mailbox()
        except Exception:
            scanner.close()
            raise
        scanner._ee_base = mailbox_host - MAP.mailbox
        return scanner

    def _scan_for_mailbox(self) -> int:
        """Scan committed memory for 'MC3A' + game CRC written by the PNACH."""
        mbi = _MBI()
        addr = ctypes.c_void_p(0)
        vqe = self._k32.VirtualQueryEx
        vqe.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPCVOID,
                        ctypes.POINTER(_MBI), ctypes.c_size_t]
        vqe.restype = ctypes.c_size_t

        marker = b"MC3A"
        crc = struct.pack("<I", GAME_CRC)
        chunk = 256 * 1024
        buf = ctypes.create_string_buffer(chunk)
        br = ctypes.c_size_t()

        while True:
            if vqe(self._h, addr, ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
                break
            if mbi.State == _MEM_COMMIT and mbi.RegionSize >= 4096:
                base = mbi.BaseAddress or 0
                for off in range(0, min(mbi.RegionSize, 150 * 1024 * 1024), chunk):
                    ok = self._rpm(self._h, ctypes.c_void_p(base + off), buf, chunk, ctypes.byref(br))
                    if not ok or br.value < 16:
                        break
                    data = buf.raw[:br.value]
                    i = 0
                    while True:
                        i = data.find(marker, i)
                        if i < 0:
                            break
                        if i + 12 <= len(data) and data[i + 8:i + 12] == crc:
                            return base + off + i
                        i += 1
            nxt = (mbi.BaseAddress or 0) + mbi.RegionSize
            if nxt <= (addr.value or 0):
                break
            addr = ctypes.c_void_p(nxt)

        raise BridgeError(
            "MC3AP mailbox not found in PCSX2 memory. "
            "Is the game booted with cheats enabled and 60A42FF5.pnach installed?"
        )

    def close(self):
        if self._h:
            self._k32.CloseHandle(self._h)
            self._h = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── EE-space primitives ──────────────────────────────────────────────

    def read(self, ee_addr: int, size: int) -> bytes:
        buf = ctypes.create_string_buffer(size)
        br = ctypes.c_size_t()
        ok = self._rpm(self._h, ctypes.c_void_p(self._ee_base + ee_addr), buf, size, ctypes.byref(br))
        if not ok:
            raise BridgeError(f"read failed at EE 0x{ee_addr:08X}")
        return buf.raw[:br.value]

    def write(self, ee_addr: int, data: bytes) -> int:
        bw = ctypes.c_size_t()
        ok = self._wpm(self._h, ctypes.c_void_p(self._ee_base + ee_addr), data, len(data), ctypes.byref(bw))
        if not ok:
            raise BridgeError(f"write failed at EE 0x{ee_addr:08X}")
        return bw.value

    def read_u32(self, ee_addr: int) -> int:
        return struct.unpack("<I", self.read(ee_addr, 4))[0]

    def write_u32(self, ee_addr: int, value: int):
        self.write(ee_addr, struct.pack("<I", value & 0xFFFFFFFF))

    def read_f32(self, ee_addr: int) -> float:
        return struct.unpack("<f", self.read(ee_addr, 4))[0]

    def read_cstring(self, ee_addr: int, max_len: int = 96) -> str:
        data = self.read(ee_addr, max_len)
        end = data.find(b"\x00")
        if end >= 0:
            data = data[:end]
        return data.decode("ascii", errors="replace")
