"""Live game monitor — watch MC3 state + detected events while you play.

    python -m mc3api.monitor            # dashboard + event log
    python -m mc3api.monitor --all      # also log every raw stat change
    python -m mc3api.monitor --interval 0.5
    python -m mc3api.monitor --legacy-dealer-probe   # also show the old,
                                                       # unproven LAYER3 probes

Top panel: current state — money, career stats, garage, and the status of
every optional AP enforcement/probe hook (purchase detect, permit deny gate,
dealer-display probe), all read through the mc3api API (mc3api.purchase_hook,
mc3api.dealer_display) rather than any standalone tool script.

Bottom: an append-only, timestamped event log — the thing to watch. Every
check-worthy change the client would act on shows here, plus:
  - DISPLAY lines the first time the dealer-display probe (if installed)
    observes a new (vehicle, class, rank, submode) combination — browse the
    showroom while this runs to build a live correlation table between the
    game's internal fields and what you see on screen (Locked/price/Owned).
  - GARAGE lines when the owned-vehicle set changes.
  - BUY lines from the exact purchase-detect hook (if installed), in addition
    to the statistical PurchaseDetected signature that always works.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .game import MC3Game
from .events import (
    CollectiblePicked, MoneyChanged, PurchaseDetected, RouteCompleted,
    StatChanged, VehiclePurchased,
)
from .stats import TAGS


# ── ANSI helpers (fall back to plain text if unsupported) ────────────────────
CSI = "\x1b["
def _c(code, s): return f"{CSI}{code}m{s}{CSI}0m"
def bold(s): return _c("1", s)
def green(s): return _c("32", s)
def yellow(s): return _c("33", s)
def cyan(s): return _c("36", s)
def red(s): return _c("31", s)
def dim(s): return _c("2", s)


TAG_LABELS = {
    TAGS.COLLECTIBLES_CITY: "collectible(city)", TAGS.COLLECTIBLES_TOTAL: "collectibles",
    TAGS.TOURNAMENT_WINS: "tournament wins", TAGS.WINS_CAREER: "wins",
    TAGS.RACES_ENTERED: "races entered", TAGS.CAREER_EARNINGS: "career $",
    TAGS.SECOND_PLACES if hasattr(TAGS, "SECOND_PLACES") else "DN2k": "2nd places",
}


def clock():
    return time.strftime("%H:%M:%S")


def describe(ev, verbose: bool) -> str | None:
    t = clock()
    if isinstance(ev, MoneyChanged):
        arrow = green(f"+{ev.delta}") if ev.delta >= 0 else red(str(ev.delta))
        return f"{dim(t)} {cyan('MONEY')}   {ev.old} -> {ev.new}  ({arrow})"
    if isinstance(ev, VehiclePurchased):
        return (f"{dim(t)} {cyan('BUY')}     {bold(ev.vehicle_name or '?')}  "
                f"spent ${ev.amount:,}  wallet {ev.wallet_before:,} -> "
                f"{ev.wallet_before - ev.amount:,}  purchase #{ev.ordinal} "
                f"{dim('(exact, via detect hook)')}")
    if isinstance(ev, PurchaseDetected):
        return (f"{dim(t)} {cyan('BUY?')}    spent ${ev.amount:,}  "
                f"wallet {ev.wallet_before:,} -> {ev.wallet_after:,}  "
                f"purchase #{ev.ordinal}  {dim('(statistical signature)')}")
    if isinstance(ev, RouteCompleted):
        tag = green("WIN ") if ev.won else yellow("done")
        return (f"{dim(t)} {cyan('RACE')}    route 0x{ev.route_id:X}  {tag}  "
                f"best {ev.best_time:.2f}s  {'-> CHECK' if ev.won else ''}")
    if isinstance(ev, CollectiblePicked):
        return f"{dim(t)} {cyan('LOGO')}    city {ev.city}  #{ev.city_count}  (total {ev.total})  -> CHECK"
    if isinstance(ev, StatChanged):
        if ev.tag == TAGS.TOURNAMENT_WINS:
            return f"{dim(t)} {cyan('TOURN')}   wins -> {ev.new}  -> CHECK"
        if verbose:
            label = TAG_LABELS.get(ev.tag, ev.tag)
            return f"{dim(t)} {dim('stat')}    {label} [{ev.tag}#{ev.index}] {ev.old} -> {ev.new}"
    return None


def _status(flag: bool) -> str:
    return green("ON") if flag else dim("off")


def garage_lines(game) -> list[str]:
    owned = game.garage_vehicles()
    names = ", ".join(owned) if owned else dim("(none)")
    return [f"  garage     {game.garage_count}/30 owned: {names}"]


def hooks_lines(game) -> list[str]:
    ring = game.purchase_ring()
    permits = game.vehicle_permits()
    probe = game.dealer_display_probe()

    detect_on = ring.installed()
    deny_on = permits.installed()
    probe_on = probe.installed()

    lines = [
        f"  hooks      detect {_status(detect_on)}   "
        f"deny {_status(deny_on)}"
    ]
    if deny_on:
        enforce = permits.read_enforce()
        denied = permits.denied_indices()
        lines[-1] += (f" enforce={'ON' if enforce else 'off'} "
                      f"permits {96 - len(denied)}/96 allowed"
                      + (f" {yellow(f'({len(denied)} denied)')}" if denied else ""))
    lines[-1] += f"   display-probe {_status(probe_on)}"
    if probe_on:
        lines[-1] += f" ({probe.call_count()} calls)"
    return lines


def legacy_dealer_lines(
    game,
    limit: int,
    dealer_report: Path | None = None,
    dealer_addresses: list[int] | None = None,
    dealer_table: int | None = None,
    scan_dealer_table: bool = False,
) -> list[str]:
    """LAYER3-era probes. The tagged-object region here was proven to be
    render OUTPUT, not the authoritative lock source — kept only for
    continuity behind --legacy-dealer-probe, not part of the default view."""
    dealer_state = game.dealer_lock_state()
    dealer_snapshot = game.dealer_rows(dealer_table, scan_dealer_table)
    dealer_rows = dealer_snapshot.rows

    lines = [
        dim(f"  [legacy] dealer   source {dealer_state.source}  mapped {dealer_state.mapped}"),
        dim(f"  [legacy] row src  {dealer_snapshot.source}  rows {len(dealer_rows)}"),
    ]
    for warning in dealer_snapshot.warnings:
        lines.append(dim(f"  [legacy] row warn {warning}"))
    if dealer_rows:
        for row in dealer_rows[:limit]:
            values = "/".join(str(value) for value in row.values)
            lines.append(dim(f"  [legacy] row      {row.index:02d} [{values}] {row.vehicle_id}"))
        if len(dealer_rows) > limit:
            lines.append(dim(f"  [legacy] row      ... +{len(dealer_rows) - limit}"))
    if dealer_report:
        try:
            probe_rows = game.dealer_probe_rows(dealer_report, dealer_addresses)
            for row in probe_rows[:limit]:
                matches = ", ".join(row.matches) if row.matches else "-"
                lines.append(dim(f"  [legacy] probe    0x{row.addr:08X}={row.current} matches {matches}"))
        except Exception as exc:
            lines.append(f"  [legacy] probe    {red('failed')} {exc}")
    return lines


def catalog_debug_lines(vehicles, limit: int) -> list[str]:
    catalog_names = ", ".join(f"{v.index}:{v.name}" for v in vehicles[:limit])
    if len(vehicles) > limit:
        catalog_names += f", ... +{len(vehicles) - limit}"
    return [
        f"  dbg catalog vehicle_list_ptr entries {len(vehicles)}",
        f"  dbg names  {dim(catalog_names or '(none)')}",
    ]


def render_header(game, ev_count, vehicle_limit: int,
                  show_catalog_debug: bool = False,
                  show_legacy_dealer: bool = False,
                  dealer_report: Path | None = None,
                  dealer_addresses: list[int] | None = None,
                  dealer_table: int | None = None,
                  scan_dealer_table: bool = False,
                  vehicles=None) -> str:
    s = game.stats.refresh()
    routes = s.completed_route_ids
    lines = [
        bold("  MC3 LIVE MONITOR") + dim(f"   (build {game.payload_build_id}, pid {game.bridge.pid})"),
        "  " + "-" * 66,
        f"  money      {bold('$' + format(game.money, ','))}"
        f"        race pos {game.live_race_position}",
        f"  wins {s.race_wins:<4} tournaments {s.tournament_wins:<4} "
        f"races {s.races_entered:<4} collectibles {s.collectibles_total}",
        f"  career $   {s.career_earnings:,}      routes done  {len(routes)}",
        f"  last event {dim(game.last_event_path or '(none)')}",
        *garage_lines(game),
        *hooks_lines(game),
    ]
    if show_legacy_dealer:
        lines += legacy_dealer_lines(game, vehicle_limit, dealer_report,
                                      dealer_addresses, dealer_table, scan_dealer_table)
    if show_catalog_debug:
        lines += catalog_debug_lines(vehicles if vehicles is not None else game.vehicles(), vehicle_limit)
    lines += [
        f"  events seen {ev_count}",
        "  " + "-" * 66,
        dim("  watching… play the game; checks/changes stream below. Ctrl-C to stop."),
    ]
    return "\n".join(lines)


class DisplayProbeTracker:
    """Emits one DISPLAY log line the first time a (vehicle, class, rank,
    submode) combination is observed. Correlate these against what you see
    on screen (Locked/price/Owned) to pin the availability predicate."""

    def __init__(self):
        self._seen: dict[int, tuple[int, int, int]] = {}

    def poll(self, game, vehicles) -> list[str]:
        probe = game.dealer_display_probe()
        if not probe.installed():
            return []
        names = {v.index: v.name for v in vehicles}
        lines = []
        for rec in probe.recent(names):
            sig = (rec.class_field, rec.rank_field, rec.submode)
            if self._seen.get(rec.vehicle_index) == sig:
                continue
            self._seen[rec.vehicle_index] = sig
            name = rec.vehicle_name or f"idx{rec.vehicle_index}"
            lines.append(
                f"{dim(clock())} {cyan('DISPLAY')} {name:<22s} idx={rec.vehicle_index:3d} "
                f"class={rec.class_field} rank={rec.rank_field} submode={rec.submode}")
        return lines


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mc3api.monitor", description="Live MC3 game monitor")
    ap.add_argument("--interval", type=float, default=0.5, help="poll seconds (default 0.5)")
    ap.add_argument("--all", action="store_true", help="log every raw stat change too")
    ap.add_argument("--plain", action="store_true",
                    help="append-only log, no screen clearing (for basic terminals)")
    ap.add_argument("--vehicles", type=int, default=12,
                    help="number of debug vehicle_list_ptr entries to show with --debug-catalog (default 12)")
    ap.add_argument("--debug-catalog", action="store_true",
                    help="show vehicle_list_ptr metadata debug lines (not lock state)")
    ap.add_argument("--legacy-dealer-probe", action="store_true",
                    help="also show the old, unproven LAYER3 dealer tagged-object probes")
    ap.add_argument("--dealer-report", type=Path,
                    help="ndiff JSON report to display live legacy probe values from")
    ap.add_argument("--dealer-address", action="append", type=lambda value: int(value, 0),
                    help="probe address from --dealer-report; repeatable")
    ap.add_argument("--dealer-table", type=lambda value: int(value, 0),
                    help="explicit legacy dealer row table address to read")
    ap.add_argument("--scan-dealer-table", action="store_true",
                    help="scan for legacy dealer row table if the fixed address has no rows")
    args = ap.parse_args(argv)

    print("mc3api.monitor — connecting to PCSX2…")
    try:
        game = MC3Game.connect(timeout=15)
    except Exception as e:
        print(f"[FAIL] {e}")
        return 1

    watcher = game.watcher()
    watcher.poll_once()  # prime baseline (don't fire for pre-existing state)
    display_tracker = DisplayProbeTracker()
    log: list[str] = []
    last_vehicle_names = [v.name for v in game.vehicles()]
    last_garage = set(game.garage_vehicles())

    def header(ev_count, vehicles=None):
        return render_header(
            game, ev_count, args.vehicles, args.debug_catalog, args.legacy_dealer_probe,
            args.dealer_report, args.dealer_address, args.dealer_table,
            args.scan_dealer_table, vehicles=vehicles)

    if args.plain:
        print(header(0))
        print(dim("  event log:"))
    else:
        sys.stdout.write("\x1b[2J\x1b[H")
        print(header(0))
        print(dim("  event log:"))

    ev_count = 0
    last_header = time.time()
    try:
        while True:
            events = watcher.poll_once()
            for ev in events:
                line = describe(ev, args.all)
                if line:
                    ev_count += 1
                    print("  " + line, flush=True)
                    log.append(line)

            vehicles = game.vehicles()

            for line in display_tracker.poll(game, vehicles):
                ev_count += 1
                print("  " + line, flush=True)
                log.append(line)

            vehicle_names = [v.name for v in vehicles]
            if vehicle_names != last_vehicle_names:
                added = [name for name in vehicle_names if name not in last_vehicle_names]
                removed = [name for name in last_vehicle_names if name not in vehicle_names]
                parts = []
                if added:
                    parts.append(green("+" + ", ".join(added[:8]) + (" ..." if len(added) > 8 else "")))
                if removed:
                    parts.append(red("-" + ", ".join(removed[:8]) + (" ..." if len(removed) > 8 else "")))
                ev_count += 1
                line = f"{dim(clock())} {cyan('VEH')}     loaded {len(last_vehicle_names)} -> {len(vehicle_names)}  {'  '.join(parts)}"
                print("  " + line, flush=True)
                log.append(line)
                last_vehicle_names = vehicle_names

            garage = set(game.garage_vehicles())
            if garage != last_garage:
                added = garage - last_garage
                removed = last_garage - garage
                parts = []
                if added:
                    parts.append(green("+" + ", ".join(sorted(added))))
                if removed:
                    parts.append(red("-" + ", ".join(sorted(removed))))
                ev_count += 1
                line = f"{dim(clock())} {cyan('GARAGE')}  {'  '.join(parts)}"
                print("  " + line, flush=True)
                log.append(line)
                last_garage = garage

            now = time.time()
            if now - last_header >= 1.0:
                last_header = now
                if args.plain:
                    # periodic compact status line, no clearing
                    s = game.stats.refresh()
                    print("  " + dim(
                        f"[{clock()}] ${game.money:,} | wins {s.race_wins} "
                        f"tourn {s.tournament_wins} logos {s.collectibles_total} "
                        f"| garage {game.garage_count}/30 | vehicles {len(vehicle_names)} "
                        f"| {ev_count} events"), flush=True)
                else:
                    saved = log[-15:]
                    sys.stdout.write("\x1b[2J\x1b[H")
                    print(header(ev_count, vehicles))
                    print(dim("  event log:"))
                    for l in saved:
                        print("  " + l)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n" + dim(f"stopped. {ev_count} events observed."))
    finally:
        game.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
