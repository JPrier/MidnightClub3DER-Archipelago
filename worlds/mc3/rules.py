"""Access rules for MC3 APWorld.

Rules are data-driven: each GateDefinition in the catalog produces
an AP access rule.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import MC3World


def apply_rules_from_gate_contract(world: "MC3World", catalog):
    """Generate AP access rules from the gate definitions in the catalog.

    For each gate, create a lambda that checks `state.has(item_name, player)`
    for all required items.
    """
    for gate in catalog.gate_table.values():
        region_name = _region_for_gate(gate, catalog)
        if region_name is None:
            continue

        region = world.multiworld.get_region(region_name, world.player)
        if region is None:
            continue

        # Build the access rule
        def _rule(state, gate=gate, player=world.player) -> bool:
            # All required items
            for item_name in gate.required_items:
                if not state.has(item_name, player):
                    return False
            # At least one of required_any
            if gate.required_any:
                if not any(
                    all(state.has(name, player) for name in group)
                    for group in gate.required_any
                ):
                    return False
            return True

        # Apply to entrance or location as appropriate
        # For city gates, apply to the entrance connecting Menu to the city
        if "city permit:" in gate.description.lower():
            for entrance in region.entrances:
                entrance.access_rule = _rule


def _region_for_gate(gate, catalog) -> str | None:
    """Map a gate to the region it protects."""
    desc = gate.description.lower()

    if "city permit:" in desc:
        city_name = desc.split("city permit:")[-1].strip()
        for city in catalog.cities.values():
            if city.name.lower() == city_name.lower():
                return city.name

    return None