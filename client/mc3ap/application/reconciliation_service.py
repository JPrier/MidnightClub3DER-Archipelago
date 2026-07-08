"""Reconciliation service — validates runtime state against desired state."""

from ..domain.reducer import DesiredGameState
from ..ports import LoggerPort


class ReconciliationService:
    """Validates that the game runtime matches the desired state."""

    def __init__(self, logger: LoggerPort = None):
        self._logger = logger

    def validate_runtime_against_desired(
        self,
        snapshot: dict,
        desired: DesiredGameState,
    ) -> list[str]:
        """Compare a RuntimeActualState snapshot against DesiredGameState.

        Returns a list of violation descriptions (empty = valid).
        """
        violations: list[str] = []

        # City check
        current_city = snapshot.get("current_city")
        if current_city and desired.allowed_cities:
            if current_city not in desired.allowed_cities:
                violations.append(f"Player in locked city: {current_city}")

        # Vehicle check
        current_vehicle = snapshot.get("current_vehicle")
        if current_vehicle and desired.allowed_vehicles:
            if current_vehicle not in desired.allowed_vehicles:
                violations.append(f"Player using locked vehicle: {current_vehicle}")

        # Money check
        actual_money = snapshot.get("money", 0)
        if actual_money < desired.total_ap_money:
            violations.append(
                f"Money below AP-granted: {actual_money} < {desired.total_ap_money}"
            )

        # Part check
        equipped = snapshot.get("equipped_parts", frozenset())
        if desired.allowed_parts:
            for part in equipped:
                if part not in desired.allowed_parts:
                    violations.append(f"Illegal part equipped: {part}")

        # Ability check
        abilities = snapshot.get("active_abilities", frozenset())
        if desired.allowed_abilities:
            for ability in abilities:
                if ability not in desired.allowed_abilities:
                    violations.append(f"Locked ability active: {ability}")

        return violations