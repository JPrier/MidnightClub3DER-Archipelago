"""Immutable ID types for all MC3 Archipelago entities.

Every domain entity gets a dedicated NewType to prevent accidental
cross-assignment and make signatures self-documenting.
"""

from typing import NewType

# ── Core ──────────────────────────────────────────────────────────────────────
ItemId = NewType("ItemId", int)
LocationId = NewType("LocationId", int)
EventId = NewType("EventId", str)
GateId = NewType("GateId", str)

# ── Geography ─────────────────────────────────────────────────────────────────
CityId = NewType("CityId", str)

# ── Vehicles ──────────────────────────────────────────────────────────────────
VehicleId = NewType("VehicleId", str)
VehicleClass = NewType("VehicleClass", str)       # D, C, B, A
VehicleCategory = NewType("VehicleCategory", str)  # Tuner, Muscle, Luxury, SUV, Exotic, SportBike, Chopper

# ── Parts & Customisation ─────────────────────────────────────────────────────
PartId = NewType("PartId", str)
PartCategoryId = NewType("PartCategoryId", str)    # Engine, Transmission, Nitrous, Tires, Suspension, etc.
CosmeticId = NewType("CosmeticId", str)

# ── Abilities ─────────────────────────────────────────────────────────────────
AbilityId = NewType("AbilityId", str)              # Zone, Agro, Roar

# ── Collectibles ──────────────────────────────────────────────────────────────
CollectibleId = NewType("CollectibleId", str)
CollectibleTier = NewType("CollectibleTier", str)  # 12, 24, 36

# ── Tournaments & Clubs ───────────────────────────────────────────────────────
TournamentId = NewType("TournamentId", str)
ClubId = NewType("ClubId", str)

# ── Rewards & Traps ───────────────────────────────────────────────────────────
RewardId = NewType("RewardId", str)
TrapId = NewType("TrapId", str)

# ── Hooks & Runtime ───────────────────────────────────────────────────────────
HookId = NewType("HookId", str)
VanillaFlagId = NewType("VanillaFlagId", str)

# ── Instance Identity ─────────────────────────────────────────────────────────
GrantedVehicleInstance = NewType("GrantedVehicleInstance", str)  # "{vehicle_id}#{ap_item_index}"