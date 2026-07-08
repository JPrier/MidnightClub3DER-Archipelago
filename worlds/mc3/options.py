"""APWorld options for MC3."""

from dataclasses import dataclass

from Options import Choice, PerGameCommonOptions, Range, Toggle


class ProgressionMode(Choice):
    """How much of the game is shuffled."""
    display_name = "Progression Mode"
    option_career = 0
    option_full = 1
    option_chaos = 2
    default = 0


class VehicleItemization(Choice):
    """How vehicles are itemized."""
    display_name = "Vehicle Itemization"
    option_permits_only = 0
    option_direct_grants = 1
    option_permits_plus_vouchers = 2
    default = 0


class PartItemization(Choice):
    """How performance parts are itemized."""
    display_name = "Part Itemization"
    option_tiers = 0
    option_categories = 1
    option_individual = 2
    default = 0


class TournamentGranularity(Choice):
    """How tournaments generate checks."""
    display_name = "Tournament Granularity"
    option_completion = 0
    option_per_race = 1
    option_both = 2
    default = 0


class ClubGranularity(Choice):
    """How club races generate checks."""
    display_name = "Club Granularity"
    option_completion = 0
    option_per_race = 1
    option_both = 2
    default = 0


class VanillaRewardPolicy(Choice):
    """How vanilla rewards are handled."""
    display_name = "Vanilla Reward Policy"
    option_suppress_ap_controlled = 0
    option_allow_cosmetic = 1
    option_vanilla = 2
    default = 0


class GarageSlotLogic(Choice):
    """How garage capacity works."""
    display_name = "Garage Slot Logic"
    option_normal = 0
    option_progressive = 1
    option_unlimited = 2
    default = 0


class StartingCityPolicy(Choice):
    """Which city the player starts in."""
    display_name = "Starting City"
    option_san_diego = 0
    option_randomized = 1
    default = 0


class StartingVehiclePolicy(Choice):
    """What vehicle the player starts with."""
    display_name = "Starting Vehicle"
    option_choose_d = 0
    option_randomized_d = 1
    option_fully_random = 2
    option_none = 3
    default = 0


class CatalogMode(Choice):
    """Which catalog to use for generation."""
    display_name = "Catalog Mode"
    option_starter = 0
    option_curated = 1
    option_generated = 2
    default = 0


@dataclass
class MC3Options(PerGameCommonOptions):
    progression_mode: ProgressionMode
    vehicle_itemization: VehicleItemization
    part_itemization: PartItemization
    tournament_granularity: TournamentGranularity
    club_granularity: ClubGranularity
    vanilla_reward_policy: VanillaRewardPolicy
    collectible_checks: Toggle
    collectible_reward_randomization: Toggle
    cosmetic_checks: Toggle
    money_checks: Toggle
    trap_percentage: Range
    garage_slot_logic: GarageSlotLogic
    starting_city_policy: StartingCityPolicy
    starting_vehicle_policy: StartingVehiclePolicy
    catalog_mode: CatalogMode