"""Port interfaces — abstract contracts that adapters implement.

The domain never imports these; the application layer depends on these
ports and adapters implement them.  This is the Dependency Inversion point.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional

from ..domain.ids import ItemId, LocationId
from ..domain.reducer import DesiredGameState
from ..domain.seed_contract import SeedContract


class APServerPort(ABC):
    """Contract for communicating with an Archipelago server."""

    @abstractmethod
    async def connect(self, slot_name: str = "") -> dict:
        ...

    @abstractmethod
    async def disconnect(self):
        ...

    @abstractmethod
    async def receive_items(self) -> List[dict]:
        """Return a list of ReceivedItems packet dicts."""

    @abstractmethod
    async def send_location_checks(self, location_ids: List[LocationId]):
        ...

    @abstractmethod
    async def send_goal(self):
        """Notify the server that the goal has been completed."""

    @abstractmethod
    async def request_sync(self) -> dict:
        """Request a full inventory resync."""


class GameRuntimePort(ABC):
    """Contract for communicating with the game runtime (via payload/PCSX2)."""

    @abstractmethod
    async def connect(self) -> bool:
        """Find and connect to the payload mailbox."""

    @abstractmethod
    async def disconnect(self):
        ...

    @abstractmethod
    async def set_desired_state(self, state: DesiredGameState):
        """Push the current desired state to the payload."""

    @abstractmethod
    async def get_runtime_snapshot(self) -> dict:
        """Request and receive a RuntimeActualState snapshot."""

    @abstractmethod
    async def events(self) -> AsyncIterator[dict]:
        """Yield game events as they arrive from the payload."""

    @abstractmethod
    async def send_command(self, command: str, payload: dict = None):
        """Send a command to the payload."""


class PersistencePort(ABC):
    """Contract for persisting client state across restarts."""

    @abstractmethod
    async def load_client_state(self) -> "ClientState":
        ...

    @abstractmethod
    async def save_client_state(self, state: "ClientState"):
        ...

    @abstractmethod
    async def record_received_item(self, ap_index: int, item_id: ItemId):
        ...

    @abstractmethod
    async def record_location_check(self, location_id: LocationId, sent_to_ap: bool = False):
        ...

    @abstractmethod
    async def record_desired_state(self, state: "DesiredGameState"):
        ...

    @abstractmethod
    async def record_game_event(self, event_type: str, payload: bytes):
        ...

    @abstractmethod
    async def get_unsent_checks(self) -> List[LocationId]:
        ...

    @abstractmethod
    async def mark_checks_sent(self, location_ids: List[LocationId]):
        ...

    @abstractmethod
    async def get_ap_connection_state(self, key: str) -> Optional[str]:
        ...

    @abstractmethod
    async def set_ap_connection_state(self, key: str, value: str):
        ...


class SeedContractPort(ABC):
    """Contract for loading the seed contract."""

    @abstractmethod
    async def load(self) -> SeedContract:
        ...


class LoggerPort(ABC):
    """Contract for logging."""

    @abstractmethod
    def info(self, msg: str, **kwargs):
        ...

    @abstractmethod
    def warning(self, msg: str, **kwargs):
        ...

    @abstractmethod
    def error(self, msg: str, **kwargs):
        ...

    @abstractmethod
    def debug(self, msg: str, **kwargs):
        ...


class ClockPort(ABC):
    """Contract for time (allows fake clock in tests)."""

    @abstractmethod
    def now_iso(self) -> str:
        ...

    @abstractmethod
    async def sleep(self, seconds: float):
        ...