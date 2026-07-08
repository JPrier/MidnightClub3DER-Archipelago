"""Region definitions for MC3 APWorld.

Regions are created data-driven from the catalog in locations.py.
This module provides helpers for region connectivity.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import MC3World


def get_menu_region(world: "MC3World") -> str:
    """The abstract 'Menu' region connects to all cities."""
    return "Menu"


def get_starting_city(world: "MC3World", catalog) -> str:
    """Determine which city the player starts in based on options."""
    if world.options.starting_city_policy.value == 1:  # randomized
        for city in catalog.cities.values():
            if city.is_starting:
                return city.name
    # Default: San Diego
    for city in catalog.cities.values():
        if city.is_starting:
            return city.name
    return "San Diego"