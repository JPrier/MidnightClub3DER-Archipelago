"""Poll-based game event detection.

Location checks do NOT require game hooks: the stats catalog plus a few
confirmed fields change deterministically on every check-worthy action.
GameWatcher polls those sources and emits typed events.

Event sources:
- LOCg / LOCc[city] increment      -> CollectiblePicked(city)
- new IT:r route id appears        -> RouteCompleted(route_id, won)
- UOTk increment                   -> StatChanged('tournament_win')
- money delta                      -> MoneyChanged(old, new)
- any other stat delta             -> StatChanged(tag, index, old, new)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

from .stats import TAGS, StatsCatalog


@dataclass(frozen=True)
class GameEvent:
    timestamp: float


@dataclass(frozen=True)
class MoneyChanged(GameEvent):
    old: int
    new: int

    @property
    def delta(self) -> int:
        return self.new - self.old


@dataclass(frozen=True)
class CollectiblePicked(GameEvent):
    city: int
    city_count: int
    total: int


@dataclass(frozen=True)
class RouteCompleted(GameEvent):
    route_id: int
    best_time: float
    won: bool           # True when a win counter incremented in the same poll


@dataclass(frozen=True)
class StatChanged(GameEvent):
    tag: str
    index: int
    old: int
    new: int


@dataclass(frozen=True)
class PurchaseDetected(GameEvent):
    """Money left the wallet without matching career earnings — a purchase.

    Signature (validated on s13->s14 dumps): spent = earnings_delta - wallet_delta.
    Covers car purchases, performance/visual upgrades, paint — the game's only
    money sinks. `ordinal` counts purchases seen this session (1-based).
    """
    amount: int
    wallet_before: int
    wallet_after: int
    ordinal: int


@dataclass(frozen=True)
class VehiclePurchased(GameEvent):
    """Exact dealer purchase captured by the detect hook (0x00337A7C).

    Unlike PurchaseDetected (a statistical wallet/earnings signature), this
    carries the actual vehicle identity and fires the instant SpendMoney runs.
    Only present when tools/hook_purchase.py has installed the detect hook.
    """
    vehicle_name: str
    amount: int
    wallet_before: int
    ordinal: int


class GameWatcher:
    """Polls game state and yields GameEvents.

    Usage:
        watcher = GameWatcher(game)
        for event in watcher.poll_forever(interval=1.0):
            ...
    or single-step:
        events = watcher.poll_once()
    """

    def __init__(self, game):
        self._game = game
        self._last_stats: Optional[Dict[Tuple[str, int], int]] = None
        self._last_money: Optional[int] = None
        self._purchase_count = 0
        # Money the watcher's owner injected since last poll (item grants /
        # refunds). Excluded from the purchase signature so applying an AP
        # money item is never mistaken for (or masks) a purchase.
        self._injected_money = 0
        # Exact-purchase ring reader — attached lazily only if the detect hook
        # is installed; otherwise stays None and poll_once skips it.
        self._purchase_ring = None
        try:
            from .purchase_hook import PurchaseRing
            ring = PurchaseRing(game.bridge)
            if ring.installed():
                self._purchase_ring = ring
        except Exception:
            self._purchase_ring = None

    def note_injected_money(self, delta: int):
        self._injected_money += delta

    def poll_once(self) -> List[GameEvent]:
        now = time.time()
        events: List[GameEvent] = []

        money = self._game.money
        stats = self._game.stats.refresh()
        snap = stats.as_dict()

        if self._last_money is not None and money != self._last_money:
            events.append(MoneyChanged(now, self._last_money, money))

        # Purchase signature: wallet dropped more than earnings explain.
        if self._last_money is not None and self._last_stats is not None:
            earn_prev = self._last_stats.get((TAGS.CAREER_EARNINGS, 0), 0)
            earn_now = snap.get((TAGS.CAREER_EARNINGS, 0), 0)
            wallet_delta = (money - self._last_money) - self._injected_money
            spent = (earn_now - earn_prev) - wallet_delta
            if spent > 0:
                self._purchase_count += 1
                events.append(PurchaseDetected(
                    now, amount=spent, wallet_before=self._last_money,
                    wallet_after=money, ordinal=self._purchase_count))
        self._injected_money = 0

        if self._last_stats is not None:
            prev = self._last_stats
            win_delta = snap.get((TAGS.WINS_CAREER, 0), 0) - prev.get((TAGS.WINS_CAREER, 0), 0)

            for key, raw in snap.items():
                tag, idx = key
                old = prev.get(key)
                if old is None:
                    # Entry inserted — first occurrence of this stat
                    if tag == TAGS.ROUTE_BEST_TIME:
                        entry = stats.get(tag, idx)
                        events.append(RouteCompleted(now, idx, entry.value, won=win_delta > 0))
                    elif tag == TAGS.COLLECTIBLES_TOTAL:
                        events.append(CollectiblePicked(
                            now, city=self._changed_city(prev, snap),
                            city_count=self._city_count(snap), total=raw))
                    else:
                        events.append(StatChanged(now, tag, idx, 0, raw))
                elif old != raw:
                    if tag == TAGS.COLLECTIBLES_TOTAL:
                        events.append(CollectiblePicked(
                            now, city=self._changed_city(prev, snap),
                            city_count=self._city_count(snap), total=raw))
                    elif tag == TAGS.ROUTE_BEST_TIME:
                        entry = stats.get(tag, idx)
                        events.append(RouteCompleted(now, idx, entry.value, won=win_delta > 0))
                    else:
                        events.append(StatChanged(now, tag, idx, old, raw))

        # Exact dealer purchases from the detect hook (if installed).
        if self._purchase_ring is not None:
            for p in self._purchase_ring.drain():
                events.append(VehiclePurchased(
                    now, vehicle_name=p.vehicle_name, amount=p.amount,
                    wallet_before=p.wallet_before, ordinal=p.ordinal))

        self._last_stats = snap
        self._last_money = money
        return events

    def poll_forever(self, interval: float = 1.0) -> Iterator[GameEvent]:
        while True:
            for ev in self.poll_once():
                yield ev
            time.sleep(interval)

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _changed_city(prev: Dict, snap: Dict) -> int:
        for city in range(8):
            key = (TAGS.COLLECTIBLES_CITY, city)
            if snap.get(key, 0) != prev.get(key, 0):
                return city
        return -1

    @staticmethod
    def _city_count(snap: Dict) -> int:
        return sum(v for (t, _), v in snap.items() if t == TAGS.COLLECTIBLES_CITY)
