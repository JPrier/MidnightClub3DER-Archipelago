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
    vehicle_count: int = 0x006E0174    # u16 — 94 in Remix (full catalog).
                                     # Read as u16! Upper 16 bits are a separate packed value.

    # ── Race state ──────────────────────────────────────────────────────
    live_race_position: int = 0x006BE4F0  # u32, 1..6 during a race

    # ── Garage (static shop/garage manager struct at 0x006E0398) ────────
    # Live-verified 2026-07-08: count=2, slot 0 name "vp_d_scion_tc_05",
    # empty slots hold the name "blank". A slot is one carCfg (0x104 bytes,
    # constructed by 0x004ADC10, copied by 0x004ADDE0).
    garage_mgr: int = 0x006E0398        # static struct base
    garage_count: int = 0x006E08FC      # u8 = garage_mgr+0x564, max 30
    garage_slots: int = 0x006E0900      # = garage_mgr+0x568, carCfg[30]
    garage_slot_stride: int = 0x104     # sizeof(carCfg) = 260
    carcfg_name_offset: int = 0xDF      # c-string vehicle name inside carCfg

    # ── Per-vehicle career records (indexed by catalog index) ───────────
    vehicle_records: int = 0x006E87F4   # = garage_mgr+0x845C, stride 0x1BC
    vehicle_record_stride: int = 0x1BC  # +0x04 updated by SpendMoney delta

    # ── Shop / purchase flow (static analysis, see artifacts/) ──────────
    shop_wallet_store: int = 0x00337A9C   # sw a3,0xAC0(v0) — wallet write in shop
    shop_spend_money_fn: int = 0x00337378 # SpendMoney(shopCtx, newTotal)
    shop_spend_money_callsite: int = 0x00337A7C  # JAL — purchase-detect hook site
    shop_buy_confirm_callsite: int = 0x003378A8  # JAL in buy path — deny hook site
    shop_handler_fn: int = 0x00337610     # "shop" Flash-UI screen handler
    purchase_pending_flag: int = 0x006179BD  # u8, set 1 on buy confirm

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
