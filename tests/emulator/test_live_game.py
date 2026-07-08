"""Emulator-backed integration tests.

These run ONLY when a PCSX2 instance with MC3 + the MC3AP pnach is live;
otherwise every test is skipped. Safe: the only write performed is a money
roundtrip that restores the original value.
"""

import pytest

from mc3api import MC3Game
from mc3api.bridge import BridgeError, PCSX2Bridge


def _live_game():
    if PCSX2Bridge.find_pid() is None:
        pytest.skip("PCSX2 not running")
    try:
        return MC3Game.connect(timeout=5)
    except BridgeError as e:
        pytest.skip(f"PCSX2 running but game/payload not ready: {e}")


@pytest.fixture(scope="module")
def game():
    g = _live_game()
    yield g
    g.close()


class TestLiveConnection:
    def test_payload_present(self, game):
        assert game.payload_build_id > 0

    def test_money_is_sane(self, game):
        assert 0 <= game.money < 100_000_000

    def test_money_write_roundtrip(self, game):
        original = game.money
        try:
            game.money = original + 1
            assert game.money == original + 1
        finally:
            game.money = original
        assert game.money == original

    def test_stats_catalog_parses(self, game):
        stats = game.stats.refresh()
        assert len(stats) >= 40           # baseline career has 46+ entries
        tags = {e.tag for e in stats}
        assert "RACk" in tags and "NIWk" in tags

    def test_stats_values_consistent(self, game):
        s = game.stats.refresh()
        assert s.races_entered >= s.race_wins  # can't win more than entered
        assert s.career_earnings >= 0

    def test_vehicle_list(self, game):
        vehicles = game.vehicles()
        assert len(vehicles) >= 10
        assert all(v.name.startswith("v") for v in vehicles[:5])

    def test_profile_pointer_valid(self, game):
        assert 0x00100000 < game.profile_addr < 0x02000000

    def test_watcher_baseline_then_idle(self, game):
        w = game.watcher()
        w.poll_once()                     # baseline
        events = w.poll_once()            # idle game -> at most timer-ish noise
        # money/collectible/route events must not appear spuriously
        from mc3api.events import CollectiblePicked, MoneyChanged, RouteCompleted
        assert not [e for e in events if isinstance(e, (MoneyChanged, CollectiblePicked, RouteCompleted))]
