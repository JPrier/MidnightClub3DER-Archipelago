"""GameRuntime adapter backed by the mc3api modding API.

Bridges the reverse-engineered live game to the client application layer:
  * detects location checks by polling the stats catalog (GameWatcher)
  * applies granted items that map to confirmed writable fields (money)
  * exposes a runtime snapshot for reconciliation

Item application philosophy:
  Only fields we can *safely* write are applied here. Money is confirmed
  writable. Vehicle/part/city gating requires blocking hooks that are not yet
  discovered, so those items are recorded as "pending" and surfaced, never
  silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .check_mapper import CheckResolver, DetectedCheck, map_event_to_checks


@dataclass
class RuntimeSnapshot:
    connected: bool
    money: int
    race_wins: int
    tournament_wins: int
    collectibles_total: int
    completed_route_ids: List[int]
    last_event_path: str
    payload_build_id: int


class MC3ApiRuntime:
    """Adapter over mc3api.MC3Game. Synchronous, poll-driven.

    Usage:
        rt = MC3ApiRuntime.connect(location_name_to_id)
        for loc_ids in rt.poll_checks():   # generator of resolved AP ids
            ap.send_location_checks(loc_ids)
    """

    def __init__(self, game, resolver: CheckResolver):
        self._game = game
        self._watcher = game.watcher()
        self._resolver = resolver
        # AP-granted target the game money should never drop below.
        self._money_floor: int = 0
        self._pending_items: List[str] = []
        # Prime the watcher baseline so we don't fire checks for pre-existing state.
        self._watcher.poll_once()

    @classmethod
    def connect(cls, location_name_to_id: Dict[str, int], timeout: float = 30.0) -> "MC3ApiRuntime":
        from mc3api import MC3Game
        game = MC3Game.connect(timeout=timeout)
        return cls(game, CheckResolver(location_name_to_id))

    def close(self):
        self._game.close()

    # ── Check detection ──────────────────────────────────────────────────

    def poll_detected_checks(self) -> List[DetectedCheck]:
        checks: List[DetectedCheck] = []
        for event in self._watcher.poll_once():
            checks.extend(map_event_to_checks(event))
        return checks

    def poll_check_ids(self) -> List[int]:
        """Return AP location ids for checks detected since the last poll."""
        return self._resolver.resolve_all(self.poll_detected_checks())

    @property
    def unresolved_checks(self) -> List[str]:
        return list(self._resolver.unresolved)

    # ── Item application ─────────────────────────────────────────────────

    def apply_money_total(self, total_ap_money: int):
        """Ensure the wallet reflects AP-granted money (idempotent).

        AP money is a running total of everything granted; we raise the game
        wallet to at least that floor without stacking on repeated applies.
        """
        self._money_floor = max(self._money_floor, total_ap_money)
        if self._game.money < self._money_floor:
            self._game.money = self._money_floor

    def record_pending_item(self, item_name: str):
        """Record an item whose in-game effect needs a not-yet-built hook."""
        self._pending_items.append(item_name)

    @property
    def pending_items(self) -> List[str]:
        return list(self._pending_items)

    # ── Reconciliation ───────────────────────────────────────────────────

    def snapshot(self) -> RuntimeSnapshot:
        s = self._game.stats.refresh()
        return RuntimeSnapshot(
            connected=True,
            money=self._game.money,
            race_wins=s.race_wins,
            tournament_wins=s.tournament_wins,
            collectibles_total=s.collectibles_total,
            completed_route_ids=s.completed_route_ids,
            last_event_path=self._game.last_event_path,
            payload_build_id=self._game.payload_build_id,
        )
