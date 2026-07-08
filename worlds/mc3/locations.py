"""APWorld location definitions for MC3."""

from typing import Dict

from BaseClasses import Location

MC3_LOCATION_BASE = 7161000

_loc_counter = MC3_LOCATION_BASE


def _next() -> int:
    global _loc_counter
    _loc_counter += 1
    return _loc_counter - 1


LOCATION_NAME_TO_ID: Dict[str, int] = {
    # City unlocks
    "City Unlocked: Atlanta":    _next(),
    "City Unlocked: Detroit":    _next(),
    "City Unlocked: Tokyo":      _next(),

    # City progression
    "City Champion Defeated: San Diego":  _next(),
    "City Champion Defeated: Atlanta":    _next(),
    "City Champion Defeated: Detroit":    _next(),
    "City Champion Defeated: Tokyo":      _next(),

    # Vehicle class & category completion
    "Vehicle Class Complete: D":  _next(),
    "Vehicle Class Complete: C":  _next(),
    "Vehicle Class Complete: B":  _next(),
    "Vehicle Class Complete: A":  _next(),
}

ID_TO_LOCATION_NAME: Dict[int, str] = {v: k for k, v in LOCATION_NAME_TO_ID.items()}


def create_regions_from_catalog(world: "MC3World", catalog):
    """Create AP regions from the game catalog.

    Each city is a region.  Races, clubs, tournaments are locations within regions.
    The Menu region is created by MC3World.create_regions() before this is called.
    """
    from BaseClasses import Region

    menu = world.multiworld.get_region("Menu", world.player)

    for city in catalog.cities.values():
        region = Region(city.name, world.player, world.multiworld)

        # Add race locations for this city
        for event_id in catalog.events_by_city.get(city.city_id, frozenset()):
            event = catalog.events.get(event_id)
            if event is None:
                continue
            loc_name = f"Race Win: {event.name}"
            loc_id = _register_location(loc_name)
            location = MC3Location(loc_id, loc_name, region.name, world.player)
            region.locations.append(location)

        # City unlock location (non-starting cities)
        if not city.is_starting:
            loc_name = f"City Unlocked: {city.name}"
            loc_id = _register_location(loc_name)
            location = MC3Location(loc_id, loc_name, region.name, world.player)
            region.locations.append(location)

        world.multiworld.regions.append(region)

    # Connect regions
    if catalog.cities:
        starting_city = next(
            (c for c in catalog.cities.values() if c.is_starting),
            list(catalog.cities.values())[0],
        )
        menu.connect(world.multiworld.get_region(starting_city.name, world.player))

        # Connect cities to menu (they share menu access)
        for city in catalog.cities.values():
            if city.is_starting:
                continue
            menu.connect(world.multiworld.get_region(city.name, world.player))


def _register_location(name: str) -> int:
    """Assign a stable numeric ID to a location name."""
    if name not in LOCATION_NAME_TO_ID:
        loc_id = _next()
        LOCATION_NAME_TO_ID[name] = loc_id
        ID_TO_LOCATION_NAME[loc_id] = name
    return LOCATION_NAME_TO_ID[name]


class MC3Location(Location):
    game = "Midnight Club 3: DUB Edition Remix"