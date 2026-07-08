"""Live game monitor — watch MC3 state + detected events while you play.

    python -m mc3api.monitor            # dashboard + event log
    python -m mc3api.monitor --all      # also log every raw stat change
    python -m mc3api.monitor --interval 0.5

Top panel: current state (refreshes in place).
Bottom: an append-only, timestamped event log — the thing to watch. Every
check-worthy change the client would act on shows here, plus (with --all) any
raw stat change so you can spot game actions the mapper doesn't yet recognize.
"""

from __future__ import annotations

import argparse
import sys
import time

from .game import MC3Game
from .events import CollectiblePicked, MoneyChanged, RouteCompleted, StatChanged
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


def render_header(game, ev_count) -> str:
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
        f"  events seen {ev_count}",
        "  " + "-" * 66,
        dim("  watching… play the game; checks/changes stream below. Ctrl-C to stop."),
    ]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mc3api.monitor", description="Live MC3 game monitor")
    ap.add_argument("--interval", type=float, default=0.5, help="poll seconds (default 0.5)")
    ap.add_argument("--all", action="store_true", help="log every raw stat change too")
    ap.add_argument("--plain", action="store_true",
                    help="append-only log, no screen clearing (for basic terminals)")
    args = ap.parse_args(argv)

    print("mc3api.monitor — connecting to PCSX2…")
    try:
        game = MC3Game.connect(timeout=15)
    except Exception as e:
        print(f"[FAIL] {e}")
        return 1

    watcher = game.watcher()
    watcher.poll_once()  # prime baseline (don't fire for pre-existing state)
    log: list[str] = []

    if args.plain:
        print(render_header(game, 0))
        print(dim("  event log:"))
    else:
        sys.stdout.write("\x1b[2J\x1b[H")
        print(render_header(game, 0))
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
            now = time.time()
            if now - last_header >= 1.0:
                last_header = now
                if args.plain:
                    # periodic compact status line, no clearing
                    s = game.stats.refresh()
                    print("  " + dim(
                        f"[{clock()}] ${game.money:,} | wins {s.race_wins} "
                        f"tourn {s.tournament_wins} logos {s.collectibles_total} "
                        f"| {ev_count} events"), flush=True)
                else:
                    saved = log[-15:]
                    sys.stdout.write("\x1b[2J\x1b[H")
                    print(render_header(game, ev_count))
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
