"""Semantic classifiers for items received from Archipelago.

Maps items to their game-world meaning so the reducer can build
DesiredGameState without hard-coding item-name parsing everywhere.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from .ids import (
    AbilityId,
    CityId,
    CollectibleTier,
    PartCategoryId,
    PartId,
    VehicleCategory,
    VehicleClass,
    VehicleId,
)


class ItemSemantic(Enum):
    CITY_PERMIT = auto()
    EVENT_PERMIT = auto()
    TOURNAMENT_PERMIT = auto()
    CLUB_PERMIT = auto()
    VEHICLE_CLASS_LICENSE = auto()
    VEHICLE_CATEGORY_PERMIT = auto()
    VEHICLE_PERMIT = auto()
    VEHICLE_GRANT = auto()
    VEHICLE_VOUCHER = auto()
    PART_PERMIT = auto()
    PART_GRANT = auto()
    PART_CATEGORY_PERMIT = auto()
    PROGRESSIVE_GARAGE_SLOT = auto()
    PROGRESSIVE_PERFORMANCE_TIER = auto()
    ABILITY_PERMIT = auto()
    MONEY_PACK = auto()
    COLLECTIBLE_REWARD = auto()
    COSMETIC_PERMIT = auto()
    TRAP = auto()
    GOAL_SENTINEL = auto()
    FILLER = auto()


@dataclass(frozen=True)
class ItemSemanticInfo:
    semantic: ItemSemantic
    city_id: Optional[CityId] = None
    event_id: Optional[str] = None
    vehicle_class: Optional[VehicleClass] = None
    vehicle_category: Optional[VehicleCategory] = None
    vehicle_id: Optional[VehicleId] = None
    part_id: Optional[PartId] = None
    part_category: Optional[PartCategoryId] = None
    ability_id: Optional[AbilityId] = None
    tier: Optional[CollectibleTier] = None
    money_amount: int = 0
    slot_count: int = 0

    @classmethod
    def filler(cls) -> "ItemSemanticInfo":
        return cls(semantic=ItemSemantic.FILLER)


# ═══════════════════════════════════════════════════════════════════════════════
#  Name → semantic parser
# ═══════════════════════════════════════════════════════════════════════════════

def classify_item_name(name: str) -> ItemSemanticInfo:
    """Parse an AP item name into structured semantics."""
    n = name.lower()

    if n.startswith("city permit:"):
        city = n.split(":", 1)[1].strip().replace(" ", "_")
        return ItemSemanticInfo(semantic=ItemSemantic.CITY_PERMIT, city_id=CityId(city))

    if n.startswith("event permit:"):
        eid = n.split(":", 1)[1].strip()
        return ItemSemanticInfo(semantic=ItemSemantic.EVENT_PERMIT, event_id=eid)

    if n.startswith("tournament permit:"):
        eid = n.split(":", 1)[1].strip()
        return ItemSemanticInfo(semantic=ItemSemantic.TOURNAMENT_PERMIT, event_id=eid)

    if n.startswith("club permit:"):
        eid = n.split(":", 1)[1].strip()
        return ItemSemanticInfo(semantic=ItemSemantic.CLUB_PERMIT, event_id=eid)

    if n.startswith("vehicle class license:"):
        vc = n.split(":", 1)[1].strip().upper()
        return ItemSemanticInfo(semantic=ItemSemantic.VEHICLE_CLASS_LICENSE, vehicle_class=VehicleClass(vc))

    if n.startswith("vehicle category permit:"):
        vc = n.split(":", 1)[1].strip().lower()
        return ItemSemanticInfo(semantic=ItemSemantic.VEHICLE_CATEGORY_PERMIT, vehicle_category=VehicleCategory(vc))

    if n.startswith("vehicle grant:"):
        vid = n.split(":", 1)[1].strip().lower().replace(" ", "_")
        return ItemSemanticInfo(semantic=ItemSemantic.VEHICLE_GRANT, vehicle_id=VehicleId(vid))

    if n.startswith("vehicle voucher:"):
        vid = n.split(":", 1)[1].strip().lower().replace(" ", "_")
        return ItemSemanticInfo(semantic=ItemSemantic.VEHICLE_VOUCHER, vehicle_id=VehicleId(vid))

    if n.startswith("vehicle permit:"):
        vid = n.split(":", 1)[1].strip().lower().replace(" ", "_")
        return ItemSemanticInfo(semantic=ItemSemantic.VEHICLE_PERMIT, vehicle_id=VehicleId(vid))

    if n.startswith("part permit:"):
        pid = n.split(":", 1)[1].strip()
        return ItemSemanticInfo(semantic=ItemSemantic.PART_PERMIT, part_id=PartId(pid))

    if n.startswith("part category permit:"):
        pc = n.split(":", 1)[1].strip().lower()
        return ItemSemanticInfo(semantic=ItemSemantic.PART_CATEGORY_PERMIT, part_category=PartCategoryId(pc))

    if n.startswith("ability permit:"):
        aid = n.split(":", 1)[1].strip().lower()
        return ItemSemanticInfo(semantic=ItemSemantic.ABILITY_PERMIT, ability_id=AbilityId(aid))

    if n.startswith("money pack:"):
        amount_str = n.split("$", 1)[1].strip().replace(",", "")
        try:
            amount = int(amount_str)
        except ValueError:
            amount = 0
        return ItemSemanticInfo(semantic=ItemSemantic.MONEY_PACK, money_amount=amount)

    if n.startswith("progressive garage slot"):
        return ItemSemanticInfo(semantic=ItemSemantic.PROGRESSIVE_GARAGE_SLOT, slot_count=1)

    if n.startswith("progressive performance tier"):
        return ItemSemanticInfo(semantic=ItemSemantic.PROGRESSIVE_PERFORMANCE_TIER)

    if n.startswith("trap:"):
        return ItemSemanticInfo(semantic=ItemSemantic.TRAP)

    if "logo reward" in n or n.startswith("rockstar logo reward"):
        tier_str = n.lower()
        if "12" in tier_str:
            tier = CollectibleTier("12_logos")
        elif "24" in tier_str:
            tier = CollectibleTier("24_logos")
        elif "36" in tier_str:
            tier = CollectibleTier("36_logos")
        else:
            tier = CollectibleTier("unknown")
        return ItemSemanticInfo(semantic=ItemSemantic.COLLECTIBLE_REWARD, tier=tier)

    if n.startswith("cosmetic "):
        return ItemSemanticInfo(semantic=ItemSemantic.COSMETIC_PERMIT)

    if n.lower() == "victory" or n.lower() == "goal":
        return ItemSemanticInfo(semantic=ItemSemantic.GOAL_SENTINEL)

    return ItemSemanticInfo.filler()