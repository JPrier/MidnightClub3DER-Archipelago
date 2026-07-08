"""Confirmed memory map for MC3: DUB Edition Remix (SLUS-21355, CRC 0x60A42FF5).

Single source of truth for EE addresses used by the API. Every entry here is
differential-proven and live-verified; see targets.yaml and docs/ for evidence.

IMPORTANT: addresses inside the stats catalog are intentionally absent —
catalog entries move (insert-shift). Use mc3api.stats.StatsCatalog instead.
"""

from dataclasses import dataclass


GAME_CRC = 0x60A42FF5
GAME_SERIAL = "SLUS-21355"

EE_RAM_SIZE = 0x02000000  # 32 MB


@dataclass(frozen=True)
class MemoryMap:
    """EE-space addresses. All confirmed via write/read roundtrip or
    multi-state differential analysis."""

    # ── Core wallet / progress ──────────────────────────────────────────
    money: int = 0x00800870            # u32, wallet cash (r/w verified)
    money_earned: int = 0x00800874     # u32
    stats_catalog_ptr: int = 0x00800878  # u32 -> catalog base (tag-scan only!)

    # ── Global pointers ─────────────────────────────────────────────────
    profile_ptr: int = 0x00619B14      # u32 -> career profile struct
    vehicle_list_ptr: int = 0x006E0170 # u32 -> vehicle array (0x54 stride)
    vehicle_count_raw: int = 0x006E0174  # non-simple format, do not trust as count

    # ── Race state ──────────────────────────────────────────────────────
    live_race_position: int = 0x006BE4F0  # u32, 1..6 during a race

    # ── Profile struct offsets (relative to *profile_ptr) ───────────────
    profile_last_event_path: int = 0x69   # c-string, last played event file path
    profile_copy_stride: int = 0x16F0     # second profile copy follows the first

    # ── MC3AP payload mailbox ───────────────────────────────────────────
    mailbox: int = 0x00720000
    mailbox_magic: int = 0x00         # +0x00 "MC3A"
    mailbox_build_id: int = 0x04      # +0x04 u32
    mailbox_game_crc: int = 0x08      # +0x08 u32
    mailbox_heartbeat_game: int = 0x0C
    mailbox_heartbeat_python: int = 0x10

    # ── Verified JAL hook sites (patch_addr, original_instr, original_target) ──
    hook_on_load_career_done: tuple = (0x001B0C20, 0x0C06C624, 0x001B1890)
    hook_set_car_cfg: tuple = (0x004AE100, 0x0C1748E0, 0x005D2380)


MAP = MemoryMap()
