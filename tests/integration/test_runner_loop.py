"""Integration test: the full client loop wiring AP items -> game effects and
game checks -> AP, driven with fakes (no socket, no emulator)."""

import pytest

from mc3api.stats import TAGS
from mc3ap.adapters.pcsx2.check_mapper import CheckResolver
from mc3ap.adapters.pcsx2.mc3api_runtime import MC3ApiRuntime
from mc3ap.runner import ItemApplier, run_client

# Reuse the fake game from the runtime test module.
from tests.integration.test_runtime_item_apply import BASE, FakeGame, f32


class FakeAP:
    def __init__(self, slot_data, item_batches):
        self.slot_data = slot_data
        self._batches = list(item_batches)
        self.sent_checks = []

    async def poll(self, timeout=None):
        return self._batches.pop(0) if self._batches else []

    async def send_location_checks(self, ids):
        self.sent_checks.extend(ids)


class RItem:
    def __init__(self, item_id):
        self.item_id = item_id


class TestItemApplier:
    def test_money_pack_parses_amount(self):
        a = ItemApplier({1: "Money Pack ($2000)"})
        game = FakeGame(6600, BASE)
        rt = MC3ApiRuntime(game, CheckResolver({}))
        assert a.apply(1, rt) == "money +2000 (total 2000)"
        assert game.money == 6600  # floor 2000 < wallet, unchanged
        # Second pack accumulates total
        a.item_id_to_name[2] = "Money x3 ($9000)"
        a.apply(2, rt)
        assert a.ap_money_total == 11000

    def test_non_money_item_is_pending(self):
        a = ItemApplier({7: "Vehicle: Lexus IS300"})
        rt = MC3ApiRuntime(FakeGame(6600, BASE), CheckResolver({}))
        assert a.apply(7, rt).startswith("pending")
        assert "Vehicle: Lexus IS300" in rt.pending_items


class TestRunnerLoop:
    async def test_one_iteration_applies_items_and_sends_checks(self):
        # slot_data supplies both maps
        slot_data = {
            "item_id_to_name": {"1": "Money Pack ($5000)"},
            "location_name_to_id": {
                "Race Win: San Diego Autocross: Ocean's Eleven Race 1": 7161500
            },
        }
        ap = FakeAP(slot_data, item_batches=[[RItem(1)]])

        game = FakeGame(6600, BASE)
        rt = MC3ApiRuntime(game, CheckResolver(
            {k: int(v) for k, v in slot_data["location_name_to_id"].items()}))

        # advance the game: win route 0x3E after the runtime baseline is primed
        after = dict(BASE)
        after[(TAGS.ROUTE_BEST_TIME, 0x3E)] = f32(61.0)
        after[(TAGS.WINS_CAREER, 0)] = 5
        game.set(6600, after)

        result = await run_client("", "Josh", _ap=ap, _runtime=rt, _once=True)

        # money item applied
        assert result["applier"].ap_money_total == 5000
        assert game.money == 6600  # 5000 floor < wallet
        # check detected and sent
        assert 7161500 in ap.sent_checks
