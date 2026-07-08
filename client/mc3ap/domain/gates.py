"""Gate evaluation engine — used by both Python reducer and C payload.

The Python version tests access in the APWorld logic layer.
The C payload version enforces access in real-time on PS2 hardware.

Both implement the same boolean algebra:
  ALL(required_items) AND ANY(required_any) AND ENOUGH(required_counts)
"""

from __future__ import annotations

from typing import FrozenSet, Mapping

from .ids import GateId
from .seed_contract import GateDecision, GateDefinition


def evaluate_gate(
    gate: GateDefinition,
    owned_item_names: FrozenSet[str],
    item_counts: Mapping[str, int],
    checked_location_names: FrozenSet[str],
) -> GateDecision:
    """Determine whether a gate is currently passable.

    Args:
        gate: the gate to evaluate
        owned_item_names: names of all items the player has received
        item_counts: how many of each item the player has
        checked_location_names: names of all locations the player has checked

    Returns:
        GateDecision with allowed=True if the gate passes
    """
    missing: list[str] = []

    # ALL required items
    for name in gate.required_items:
        if name not in owned_item_names:
            missing.append(name)

    # ANY(required_any) — at least one group must be fully satisfied
    if gate.required_any:
        any_satisfied = False
        for group in gate.required_any:
            if all(name in owned_item_names for name in group):
                any_satisfied = True
                break
        if not any_satisfied:
            missing.append(" | ".join(
                "(" + " + ".join(sorted(g)) + ")"
                for g in gate.required_any
            ))

    # required_counts
    for name, needed in gate.required_counts.items():
        if item_counts.get(name, 0) < needed:
            missing.append(f"{name} x{needed}")

    # required_locations
    for loc_name in gate.required_locations:
        if loc_name not in checked_location_names:
            missing.append(f"loc:{loc_name}")

    if missing:
        return GateDecision(
            allowed=False,
            reason_code=1,
            missing_gate_id=", ".join(missing),
        )

    return GateDecision(allowed=True)


def evaluate_all_gates(
    gates: Mapping[GateId, GateDefinition],
    owned_item_names: FrozenSet[str],
    item_counts: Mapping[str, int],
    checked_location_names: FrozenSet[str],
) -> Mapping[GateId, GateDecision]:
    """Evaluate every gate and return results."""
    return {
        gid: evaluate_gate(gate, owned_item_names, item_counts, checked_location_names)
        for gid, gate in gates.items()
    }