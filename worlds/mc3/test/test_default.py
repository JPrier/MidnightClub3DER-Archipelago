"""Default generation tests for MC3 APWorld."""

from .bases import MC3TestBase


class TestDefault(MC3TestBase):
    """Verify the world generates with default options."""

    def test_all_state_can_reach_everything(self):
        """All items collected → all locations reachable."""
        self.assertAccessDependency(self.multiworld.state, [])

    def test_empty_state_can_reach_something(self):
        """With no items, at least something should be reachable."""
        reachable = self.get_reachable_locations()
        self.assertGreater(len(reachable), 0, "No locations reachable from start")