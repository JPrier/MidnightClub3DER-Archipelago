"""Runnable MC3 Archipelago client — glues the AP websocket client to the
live game via mc3api. This is the concrete entry point players use.

    python -m mc3ap --server wss://archipelago.gg:38281 --slot Josh

The reconciliation logic (how an AP item affects the game) is factored into
pure helpers (`ItemApplier`) so it is unit-testable without a socket or an
emulator.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


# ── Item application policy (pure/testable) ──────────────────────────────────

@dataclass
class ItemApplier:
    """Translate AP item ids into game effects against a runtime.

    Item semantics come from slot_data's item_id -> name map. Money items add
    to a running AP-money total (applied as a wallet floor); everything else is
    recorded as pending until its gating hook exists.
    """
    item_id_to_name: Dict[int, str]
    money_per_pack: int = 1000
    ap_money_total: int = 0
    applied_pending: List[str] = field(default_factory=list)

    def money_amount_for(self, name: str) -> int:
        """Return the cash value of a money item, else 0.

        Only treats an item as money when it is explicitly a money item — a
        '$' amount, or the word 'money'/'cash'. Avoids false positives like a
        vehicle named 'IS300'.
        """
        import re
        is_money = "money" in name.lower() or "cash" in name.lower()
        dollar = re.search(r"\$\s*(\d[\d,]*)", name)
        if dollar:
            return int(dollar.group(1).replace(",", ""))
        if is_money:
            num = re.search(r"(\d[\d,]*)", name)
            return int(num.group(1).replace(",", "")) if num else self.money_per_pack
        return 0

    def apply(self, item_id: int, runtime) -> str:
        """Apply one received item. Returns a short description of what happened."""
        name = self.item_id_to_name.get(item_id, f"item#{item_id}")
        amount = self.money_amount_for(name)
        if amount > 0:
            self.ap_money_total += amount
            runtime.apply_money_total(self.ap_money_total)
            return f"money +{amount} (total {self.ap_money_total})"
        # Non-money items need in-game gating hooks not yet built.
        runtime.record_pending_item(name)
        self.applied_pending.append(name)
        return f"pending: {name}"


# ── Async client loop ────────────────────────────────────────────────────────

async def run_client(server: str, slot: str, password: str = "",
                     poll_interval: float = 1.0, log=print,
                     _ap=None, _runtime=None, _once=False):
    """Connect to AP + game and run the reconcile loop.

    _ap / _runtime injection points let tests drive the loop with fakes.
    _once runs a single iteration (for tests) then returns.
    """
    from .adapters.archipelago.ap_client_adapter import ArchipelagoClient

    game_name = "Midnight Club 3: DUB Edition Remix"
    ap = _ap or ArchipelagoClient(game_name)
    if _ap is None:
        connected = await ap.connect(server, slot, password)
        log(f"[AP] connected as {slot}; slot_data keys: {list(ap.slot_data.keys())}")
    else:
        connected = {"slot_data": ap.slot_data}

    # Build item-id -> name and location-name -> id from slot_data (fallbacks empty).
    item_map = {int(k): v for k, v in ap.slot_data.get("item_id_to_name", {}).items()}
    loc_map = {k: int(v) for k, v in ap.slot_data.get("location_name_to_id", {}).items()}

    from .adapters.pcsx2.mc3api_runtime import MC3ApiRuntime
    from .adapters.pcsx2.check_mapper import CheckResolver
    if _runtime is not None:
        runtime = _runtime
    else:
        runtime = MC3ApiRuntime.connect(loc_map)
        log(f"[GAME] connected; payload build {runtime.snapshot().payload_build_id}")

    applier = ItemApplier(item_map)

    async def one_iteration():
        # 1. Receive items from AP and apply them.
        try:
            new_items = await ap.poll()
        except Exception as e:  # transient socket read
            log(f"[AP] poll error: {e}")
            new_items = []
        for it in new_items:
            desc = applier.apply(it.item_id, runtime)
            log(f"[ITEM] {desc}")
        # 2. Detect in-game checks and send them.
        check_ids = runtime.poll_check_ids()
        if check_ids:
            await ap.send_location_checks(check_ids)
            log(f"[CHECK] sent {check_ids}")
        if runtime.unresolved_checks:
            log(f"[WARN] unmapped checks: {runtime.unresolved_checks}")

    if _once:
        await one_iteration()
        return {"applier": applier, "runtime": runtime}

    log("[RUN] entering main loop (Ctrl-C to stop)")
    try:
        while True:
            await one_iteration()
            await asyncio.sleep(poll_interval)
    except (KeyboardInterrupt, asyncio.CancelledError):
        log("[RUN] shutting down")
    finally:
        if _ap is None:
            await ap.disconnect()
        if _runtime is None:
            runtime.close()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mc3ap", description="MC3 Archipelago client")
    ap.add_argument("--server", required=True, help="AP server url, e.g. wss://archipelago.gg:38281")
    ap.add_argument("--slot", required=True, help="Your slot name")
    ap.add_argument("--password", default="", help="Server password (if any)")
    ap.add_argument("--interval", type=float, default=1.0, help="Poll interval seconds")
    args = ap.parse_args(argv)
    asyncio.run(run_client(args.server, args.slot, args.password, args.interval))


if __name__ == "__main__":
    main()
