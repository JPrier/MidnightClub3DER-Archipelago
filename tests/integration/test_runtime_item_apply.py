"""Integration test: MC3ApiRuntime item application + check detection
against a fake game (no emulator)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "client"))

from mc3api.stats import TAGS
from mc3ap.adapters.pcsx2.check_mapper import CheckResolver
from mc3ap.adapters.pcsx2.mc3api_runtime import MC3ApiRuntime


def f32(v):
    import struct
    return struct.unpack("<I", struct.pack("<f", v))[0]


class FakeStats:
    def __init__(self, snap):
        self._snap = dict(snap)

    def refresh(self):
        return self

    def as_dict(self):
        return dict(self._snap)

    def get(self, tag, idx):
        raw = self._snap.get((tag, idx))
        if raw is None:
            return None
        import struct
        val = struct.unpack("<f", struct.pack("<I", raw))[0] if tag in ("IT:r", "PSAr") else raw
        return type("E", (), {"value": val})()

    # semantic accessors used by snapshot()
    @property
    def race_wins(self):
        return self._snap.get((TAGS.WINS_CAREER, 0), 0)

    @property
    def tournament_wins(self):
        return self._snap.get((TAGS.TOURNAMENT_WINS, 0), 0)

    @property
    def collectibles_total(self):
        for (t, _), v in self._snap.items():
            if t == TAGS.COLLECTIBLES_TOTAL:
                return v
        return 0

    @property
    def completed_route_ids(self):
        return sorted(i for (t, i) in self._snap if t == TAGS.ROUTE_BEST_TIME)


class FakeGame:
    def __init__(self, money, snap):
        self.money = money
        self.stats = FakeStats(snap)
        self.last_event_path = ""
        self.payload_build_id = 13

    def watcher(self):
        from mc3api.events import GameWatcher
        return GameWatcher(self)

    def set(self, money, snap):
        self.money = money
        self.stats = FakeStats(snap)

    def close(self):
        pass


BASE = {
    (TAGS.WINS_CAREER, 0): 4,
    (TAGS.TOURNAMENT_WINS, 0): 0,
    (TAGS.ROUTE_BEST_TIME, 0x1): f32(76.0),
}

TABLE = {
    "Race Win: San Diego Autocross: Ocean's Eleven Race 1": 7161500,
    "Tournament Won #1": 7161600,
}


def make_runtime(game):
    return MC3ApiRuntime(game, CheckResolver(TABLE))


class TestItemApplication:
    def test_money_floor_raises_wallet(self):
        game = FakeGame(6600, BASE)
        rt = make_runtime(game)
        rt.apply_money_total(10000)
        assert game.money == 10000

    def test_money_apply_is_idempotent(self):
        game = FakeGame(6600, BASE)
        rt = make_runtime(game)
        rt.apply_money_total(10000)
        game.money = 8000  # player spent some
        rt.apply_money_total(10000)  # same AP total -> do NOT re-stack
        assert game.money == 10000

    def test_money_never_lowers_wallet(self):
        game = FakeGame(50000, BASE)
        rt = make_runtime(game)
        rt.apply_money_total(10000)
        assert game.money == 50000  # richer than AP floor, untouched

    def test_pending_items_tracked(self):
        rt = make_runtime(FakeGame(6600, BASE))
        rt.record_pending_item("Vehicle: Lexus IS300")
        assert rt.pending_items == ["Vehicle: Lexus IS300"]


class TestCheckDetection:
    def test_win_route_detected_and_resolved(self):
        game = FakeGame(6600, BASE)
        rt = make_runtime(game)  # primes baseline
        after = dict(BASE)
        after[(TAGS.ROUTE_BEST_TIME, 0x3E)] = f32(61.0)
        after[(TAGS.WINS_CAREER, 0)] = 5
        game.set(6600, after)
        ids = rt.poll_check_ids()
        assert 7161500 in ids

    def test_tournament_win_detected(self):
        game = FakeGame(6600, BASE)
        rt = make_runtime(game)
        after = dict(BASE)
        after[(TAGS.TOURNAMENT_WINS, 0)] = 1
        game.set(6600, after)
        ids = rt.poll_check_ids()
        assert 7161600 in ids

    def test_no_spurious_checks_when_idle(self):
        game = FakeGame(6600, BASE)
        rt = make_runtime(game)
        assert rt.poll_check_ids() == []

    def test_snapshot_reports_state(self):
        game = FakeGame(13900, BASE)
        rt = make_runtime(game)
        snap = rt.snapshot()
        assert snap.money == 13900
        assert snap.race_wins == 4
        assert snap.completed_route_ids == [0x1]
