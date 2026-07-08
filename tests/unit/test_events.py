"""Unit tests for GameWatcher event detection using a fake game."""

from typing import Dict, List, Tuple

from mc3api.events import (
    CollectiblePicked,
    GameWatcher,
    MoneyChanged,
    RouteCompleted,
    StatChanged,
)
from mc3api.stats import TAGS


class FakeStats:
    def __init__(self, snap: Dict[Tuple[str, int], int]):
        self._snap = dict(snap)

    def refresh(self):
        return self

    def as_dict(self):
        return dict(self._snap)

    def get(self, tag, idx):
        class E:
            def __init__(self, raw):
                import struct
                self.value = struct.unpack("<f", struct.pack("<I", raw))[0] \
                    if tag in ("IT:r", "PSAr") else raw
        raw = self._snap.get((tag, idx))
        return E(raw) if raw is not None else None


class FakeGame:
    def __init__(self):
        self.money = 6600
        self.stats = FakeStats({})

    def set_state(self, money, snap):
        self.money = money
        self.stats = FakeStats(snap)


def f32(v: float) -> int:
    import struct
    return struct.unpack("<I", struct.pack("<f", v))[0]


BASE = {
    (TAGS.COLLECTIBLES_CITY, 0): 0,
    (TAGS.WINS_CAREER, 0): 4,
    (TAGS.TOURNAMENT_WINS, 0): 0,
    ("IT:r", 0x1): f32(76.354),
}


def make_watcher(game):
    w = GameWatcher(game)
    w.poll_once()  # baseline
    return w


class TestGameWatcher:
    def test_no_change_no_events(self):
        game = FakeGame()
        game.set_state(6600, BASE)
        w = make_watcher(game)
        assert w.poll_once() == []

    def test_money_change(self):
        game = FakeGame()
        game.set_state(6600, BASE)
        w = make_watcher(game)
        game.set_state(7300, BASE)
        events = w.poll_once()
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, MoneyChanged)
        assert ev.delta == 700

    def test_collectible_pickup_first_ever(self):
        game = FakeGame()
        game.set_state(6600, BASE)
        w = make_watcher(game)
        after = dict(BASE)
        after[(TAGS.COLLECTIBLES_CITY, 0)] = 1
        after[(TAGS.COLLECTIBLES_TOTAL, 0xFFFF0000)] = 1  # inserted entry
        game.set_state(6600, after)
        events = w.poll_once()
        picks = [e for e in events if isinstance(e, CollectiblePicked)]
        assert len(picks) == 1
        assert picks[0].city == 0
        assert picks[0].total == 1

    def test_route_completed_with_win(self):
        game = FakeGame()
        game.set_state(6600, BASE)
        w = make_watcher(game)
        after = dict(BASE)
        after[("IT:r", 0x3E)] = f32(61.011)      # new route record
        after[(TAGS.WINS_CAREER, 0)] = 5          # won it
        game.set_state(6600, after)
        events = w.poll_once()
        routes = [e for e in events if isinstance(e, RouteCompleted)]
        assert len(routes) == 1
        assert routes[0].route_id == 0x3E
        assert routes[0].won is True

    def test_route_completed_without_win(self):
        game = FakeGame()
        game.set_state(6600, BASE)
        w = make_watcher(game)
        after = dict(BASE)
        after[("IT:r", 0x3F)] = f32(45.9)
        game.set_state(6600, after)
        routes = [e for e in w.poll_once() if isinstance(e, RouteCompleted)]
        assert len(routes) == 1
        assert routes[0].won is False

    def test_tournament_win_stat_change(self):
        game = FakeGame()
        game.set_state(6600, BASE)
        w = make_watcher(game)
        after = dict(BASE)
        after[(TAGS.TOURNAMENT_WINS, 0)] = 1
        game.set_state(6600, after)
        stats = [e for e in w.poll_once() if isinstance(e, StatChanged)]
        assert any(e.tag == TAGS.TOURNAMENT_WINS and e.new == 1 for e in stats)
