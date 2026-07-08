"""Scenario runner for validation tests.

Scenarios are YAML files under scenarios/ that define:
  given: initial DesiredGameState
  actions: sequence of player actions (e.g. travel, race, purchase)
  expect: expected outcomes (gate blocked, check emitted, state changed)

The runner loads a scenario, executes it against a FakeGameRuntime,
and asserts the expected outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class Scenario:
    name: str
    given: Dict[str, Any]
    actions: List[Dict[str, Any]]
    expect: Dict[str, Any]


def load_scenario(path: Path) -> Scenario:
    with open(path) as f:
        data = yaml.safe_load(f)
    return Scenario(
        name=data["name"],
        given=data.get("given", {}),
        actions=data.get("actions", []),
        expect=data.get("expect", {}),
    )


def load_all_scenarios(scenarios_dir: Path) -> List[Scenario]:
    """Load all .yaml scenario files from a directory."""
    scenarios = []
    for yaml_file in sorted(scenarios_dir.glob("*.yaml")):
        scenarios.append(load_scenario(yaml_file))
    return scenarios


class ScenarioResult:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.passed = False
        self.errors: List[str] = []

    def __repr__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"{status}: {self.scenario.name}"


class ScenarioRunner:
    """Runs validation scenarios against a game runtime."""

    def __init__(self, runtime):
        self._runtime = runtime

    def run(self, scenario: Scenario) -> ScenarioResult:
        result = ScenarioResult(scenario)

        # Apply initial desired state
        if scenario.given:
            desired = scenario.given.get("desired_state", {})
            # TODO: parse and apply DesiredGameState
            self._runtime.reconcile()

        # Execute actions
        events: list = []
        self._runtime.events.clear()

        for action in scenario.actions:
            action_type = list(action.keys())[0]
            action_value = action[action_type]

            if action_type == "travel_to":
                ok = self._runtime.travel_to_city(action_value)
                events.append({"action": action_type, "result": ok})
            elif action_type == "select_event":
                self._runtime.select_event(action_value)
            elif action_type == "attempt_start_event":
                ok = self._runtime.attempt_start_event(action_value)
                events.append({"action": action_type, "result": ok})
            elif action_type == "complete_race":
                self._runtime.complete_race(won=action_value.get("won", True))
            elif action_type == "purchase_vehicle":
                ok = self._runtime.purchase_vehicle(action_value)
                events.append({"action": action_type, "result": ok})
            elif action_type == "collect_logo":
                ok = self._runtime.collect_logo(action_value)
                events.append({"action": action_type, "result": ok})

        # Check expectations
        for key, expected in scenario.expect.items():
            if key == "gate_blocked":
                actual = any(e.get("type") == "gate_blocked" for e in self._runtime.events)
                if actual != expected:
                    result.errors.append(f"Expected gate_blocked={expected}, got {actual}")
            elif key == "location_checked":
                # Check that a specific location was emitted
                checked = [
                    e.get("location_id")
                    for e in self._runtime.events
                    if e.get("type") == "location_checked"
                ]
                if expected not in checked:
                    result.errors.append(f"Expected check {expected}, got {checked}")

        result.passed = len(result.errors) == 0
        return result


if __name__ == "__main__":
    # Quick smoke test
    from ..adapters.fake.fake_game_runtime import FakeGameRuntime

    runner = ScenarioRunner(FakeGameRuntime())
    scenario = Scenario(
        name="smoke",
        given={},
        actions=[{"travel_to": "tokyo"}],
        expect={},
    )
    result = runner.run(scenario)
    print(result)