"""Unit tests for monitor.py's data-formatting/dedup logic (no emulator)."""

from mc3api.monitor import DisplayProbeTracker, garage_lines, hooks_lines
from mc3api.dealer_display import DisplayProbeRecord


class FakeVehicle:
    def __init__(self, index, name):
        self.index = index
        self.name = name


class FakePurchaseRing:
    def __init__(self, installed=True):
        self._installed = installed

    def installed(self):
        return self._installed


class FakePermitTable:
    def __init__(self, installed=True, enforce=False, denied=()):
        self._installed = installed
        self._enforce = enforce
        self._denied = list(denied)

    def installed(self):
        return self._installed

    def read_enforce(self):
        return self._enforce

    def denied_indices(self):
        return self._denied


class FakeDisplayProbe:
    def __init__(self, installed=True, count=0, records=()):
        self._installed = installed
        self._count = count
        self._records = list(records)

    def installed(self):
        return self._installed

    def call_count(self):
        return self._count

    def recent(self, names=None):
        return self._records


class FakeGame:
    def __init__(self, garage_count=0, garage=(), ring=None, permits=None, probe=None):
        self.garage_count = garage_count
        self._garage = list(garage)
        self._ring = ring or FakePurchaseRing()
        self._permits = permits or FakePermitTable()
        self._probe = probe or FakeDisplayProbe()

    def garage_vehicles(self):
        return self._garage

    def purchase_ring(self):
        return self._ring

    def vehicle_permits(self):
        return self._permits

    def dealer_display_probe(self):
        return self._probe

    def vehicles(self):
        return []


def strip_ansi(s: str) -> str:
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


class TestGarageLines:
    def test_empty_garage(self):
        game = FakeGame(garage_count=0, garage=[])
        line = strip_ansi(garage_lines(game)[0])
        assert "0/30 owned" in line
        assert "(none)" in line

    def test_owned_vehicles_listed(self):
        game = FakeGame(garage_count=2, garage=["vp_d_scion_tc_05", "vp_is300_04"])
        line = strip_ansi(garage_lines(game)[0])
        assert "2/30 owned" in line
        assert "vp_d_scion_tc_05" in line
        assert "vp_is300_04" in line


class TestHooksLines:
    def test_all_off(self):
        game = FakeGame(
            ring=FakePurchaseRing(installed=False),
            permits=FakePermitTable(installed=False),
            probe=FakeDisplayProbe(installed=False))
        line = strip_ansi(hooks_lines(game)[0])
        assert "detect off" in line
        assert "deny off" in line
        assert "display-probe off" in line
        assert "enforce" not in line   # only shown when deny is installed

    def test_deny_installed_shows_enforce_and_permits(self):
        game = FakeGame(
            ring=FakePurchaseRing(installed=True),
            permits=FakePermitTable(installed=True, enforce=True, denied=[4, 69]),
            probe=FakeDisplayProbe(installed=True, count=17))
        line = strip_ansi(hooks_lines(game)[0])
        assert "detect ON" in line
        assert "deny ON" in line
        assert "enforce=ON" in line
        assert "94/96 allowed" in line
        assert "2 denied" in line
        assert "display-probe ON" in line
        assert "17 calls" in line

    def test_deny_not_installed_omits_permit_detail(self):
        game = FakeGame(permits=FakePermitTable(installed=False))
        line = strip_ansi(hooks_lines(game)[0])
        assert "permits" not in line


class TestDisplayProbeTracker:
    def test_no_lines_when_not_installed(self):
        game = FakeGame(probe=FakeDisplayProbe(installed=False))
        tracker = DisplayProbeTracker()
        assert tracker.poll(game, []) == []

    def test_emits_once_per_unique_signature(self):
        rec = DisplayProbeRecord(4, "vp_is300_04", 0, 0, 25)
        game = FakeGame(probe=FakeDisplayProbe(installed=True, records=[rec]))
        tracker = DisplayProbeTracker()

        first = tracker.poll(game, [])
        assert len(first) == 1
        assert "vp_is300_04" in first[0]
        assert "class=0" in first[0]
        assert "rank=0" in first[0]
        assert "submode=25" in first[0]

        # same signature again -> no new line
        assert tracker.poll(game, []) == []

    def test_emits_again_when_submode_changes(self):
        game = FakeGame(probe=FakeDisplayProbe(
            installed=True, records=[DisplayProbeRecord(4, "vp_is300_04", 0, 0, 25)]))
        tracker = DisplayProbeTracker()
        assert len(tracker.poll(game, [])) == 1

        game._probe._records = [DisplayProbeRecord(4, "vp_is300_04", 0, 0, 39)]
        second = tracker.poll(game, [])
        assert len(second) == 1
        assert "submode=39" in second[0]
