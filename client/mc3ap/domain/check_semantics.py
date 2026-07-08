"""Semantic classifiers for locations checked in-game.

Maps location names to their game-world meaning for validation.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from .ids import CityId, CollectibleId, EventId, VehicleId


class CheckSemantic(Enum):
    RACE_WIN = auto()
    TOURNAMENT_COMPLETE = auto()
    TOURNAMENT_RACE_WIN = auto()
    CLUB_RACE_WIN = auto()
    CLUB_COMPLETE = auto()
    CITY_UNLOCKED = auto()
    CITY_CHAMPION_DEFEATED = auto()
    VEHICLE_PURCHASED = auto()
    VEHICLE_OWNED = auto()
    VEHICLE_WON = auto()
    VEHICLE_CATEGORY_COMPLETE = auto()
    VEHICLE_CLASS_COMPLETE = auto()
    PART_PURCHASED = auto()
    PART_EQUIPPED = auto()
    FULL_TIER_EQUIPPED = auto()
    FULL_VISUAL_KIT_EQUIPPED = auto()
    COLLECTIBLE_PICKUP = auto()
    COLLECTIBLE_TIER = auto()
    COSMETIC_UNLOCKED = auto()
    COSMETIC_PURCHASED = auto()
    MONEY_EARNED = auto()
    MONEY_SPENT = auto()
    GOAL = auto()


@dataclass(frozen=True)
class CheckSemanticInfo:
    semantic: CheckSemantic
    event_id: Optional[EventId] = None
    city_id: Optional[CityId] = None
    vehicle_id: Optional[VehicleId] = None
    collectible_id: Optional[CollectibleId] = None
    tier: Optional[str] = None
    is_meta_check: bool = False


def classify_check_name(name: str) -> CheckSemanticInfo:
    """Parse a check/location name into structured semantics."""
    n = name.lower()

    if n.startswith("race win:"):
        eid = n.split(":", 1)[1].strip()
        return CheckSemanticInfo(semantic=CheckSemantic.RACE_WIN, event_id=EventId(eid))

    if n.startswith("tournament complete:"):
        eid = n.split(":", 1)[1].strip()
        return CheckSemanticInfo(semantic=CheckSemantic.TOURNAMENT_COMPLETE, event_id=EventId(eid), is_meta_check=True)

    if n.startswith("tournament race win:"):
        eid = n.split(":", 1)[1].strip()
        return CheckSemanticInfo(semantic=CheckSemantic.TOURNAMENT_RACE_WIN, event_id=EventId(eid))

    if n.startswith("club race win:"):
        eid = n.split(":", 1)[1].strip()
        return CheckSemanticInfo(semantic=CheckSemantic.CLUB_RACE_WIN, event_id=EventId(eid))

    if n.startswith("club complete:"):
        eid = n.split(":", 1)[1].strip()
        return CheckSemanticInfo(semantic=CheckSemantic.CLUB_COMPLETE, event_id=EventId(eid), is_meta_check=True)

    if n.startswith("city unlocked:"):
        city = n.split(":", 1)[1].strip().lower().replace(" ", "_")
        return CheckSemanticInfo(semantic=CheckSemantic.CITY_UNLOCKED, city_id=CityId(city))

    if n.startswith("city champion defeated:"):
        city = n.split(":", 1)[1].strip().lower().replace(" ", "_")
        return CheckSemanticInfo(semantic=CheckSemantic.CITY_CHAMPION_DEFEATED, city_id=CityId(city))

    if n.startswith("vehicle purchased:"):
        vid = n.split(":", 1)[1].strip().lower().replace(" ", "_")
        return CheckSemanticInfo(semantic=CheckSemantic.VEHICLE_PURCHASED, vehicle_id=VehicleId(vid))

    if n.startswith("vehicle owned:"):
        vid = n.split(":", 1)[1].strip().lower().replace(" ", "_")
        return CheckSemanticInfo(semantic=CheckSemantic.VEHICLE_OWNED, vehicle_id=VehicleId(vid))

    if n.startswith("vehicle won:"):
        vid = n.split(":", 1)[1].strip().lower().replace(" ", "_")
        return CheckSemanticInfo(semantic=CheckSemantic.VEHICLE_WON, vehicle_id=VehicleId(vid))

    if n.startswith("vehicle category complete:"):
        cat = n.split(":", 1)[1].strip().lower()
        return CheckSemanticInfo(semantic=CheckSemantic.VEHICLE_CATEGORY_COMPLETE, is_meta_check=True)

    if n.startswith("vehicle class complete:"):
        return CheckSemanticInfo(semantic=CheckSemantic.VEHICLE_CLASS_COMPLETE, is_meta_check=True)

    if n.startswith("part purchased:"):
        pid = n.split(":", 1)[1].strip()
        return CheckSemanticInfo(semantic=CheckSemantic.PART_PURCHASED)

    if n.startswith("part equipped:"):
        pid = n.split(":", 1)[1].strip()
        return CheckSemanticInfo(semantic=CheckSemantic.PART_EQUIPPED)

    if n.startswith("rockstar logo collected:"):
        cid = n.split(":", 1)[1].strip()
        return CheckSemanticInfo(semantic=CheckSemantic.COLLECTIBLE_PICKUP, collectible_id=CollectibleId(cid))

    if "logos collected" in n:
        tier_str = n.strip()
        return CheckSemanticInfo(semantic=CheckSemantic.COLLECTIBLE_TIER, tier=tier_str, is_meta_check=True)

    if "goal" in n or "victory" in n:
        return CheckSemanticInfo(semantic=CheckSemantic.GOAL)

    return CheckSemanticInfo(semantic=CheckSemantic.GOAL)