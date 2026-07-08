"""Integration tests: game events -> AP location checks.

No emulator needed; drives the mapper with synthetic mc3api events.
"""

import pytest

from mc3api.events import CollectiblePicked, MoneyChanged, RouteCompleted, StatChanged
from mc3api.stats import TAGS

from mc3ap.adapters.pcsx2.check_mapper import (
    CheckResolver,
    map_event_to_checks,
    route_location_name,
    tournament_location_name,
)


def t():
    return 1000.0  # fixed timestamp (Date.now unavailable / determinism)


class TestEventMapping:
    def test_won_route_produces_check(self):
        checks = map_event_to_checks(RouteCompleted(t(), route_id=0x3E, best_time=61.0, won=True))
        assert len(checks) == 1
        assert checks[0].source == "route"
        assert checks[0].location_name == "Race Win: San Diego Autocross: Ocean's Eleven Race 1"

    def test_lost_route_produces_no_check(self):
        checks = map_event_to_checks(RouteCompleted(t(), route_id=0x3E, best_time=61.0, won=False))
        assert checks == []

    def test_unknown_route_still_named_deterministically(self):
        name = route_location_name(0xAB)
        assert name == "Race Win: Route 0xAB"
        checks = map_event_to_checks(RouteCompleted(t(), route_id=0xAB, best_time=10.0, won=True))
        assert checks[0].location_name == name

    def test_collectible_maps_to_city_ordinal(self):
        checks = map_event_to_checks(CollectiblePicked(t(), city=0, city_count=1, total=1))
        assert len(checks) == 1
        assert checks[0].location_name == "Collectible: San Diego #1"

    def test_tournament_win_maps(self):
        checks = map_event_to_checks(StatChanged(t(), tag=TAGS.TOURNAMENT_WINS, index=0, old=0, new=1))
        assert checks[0].location_name == tournament_location_name(1)

    def test_money_change_is_not_a_check(self):
        assert map_event_to_checks(MoneyChanged(t(), old=1, new=2)) == []

    def test_unrelated_stat_is_not_a_check(self):
        assert map_event_to_checks(StatChanged(t(), tag="RACk", index=0, old=10, new=11)) == []


class TestCheckResolver:
    def test_resolves_known_names(self):
        table = {"Race Win: Route 0xAB": 7161999}
        r = CheckResolver(table)
        checks = map_event_to_checks(RouteCompleted(t(), route_id=0xAB, best_time=1.0, won=True))
        assert r.resolve_all(checks) == [7161999]
        assert r.unresolved == []

    def test_records_unresolved(self):
        r = CheckResolver({})
        checks = map_event_to_checks(RouteCompleted(t(), route_id=0xAB, best_time=1.0, won=True))
        assert r.resolve_all(checks) == []
        assert r.unresolved == ["Race Win: Route 0xAB"]
