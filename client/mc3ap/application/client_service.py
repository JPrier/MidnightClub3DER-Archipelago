"""MC3AP Client Application Service.

Orchestrates the main loop: AP connection, item processing,
game reconciliation, and event dispatch.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from ..domain.reducer import (
    ClientState,
    DesiredGameState,
    apply_full_inventory_reset,
    apply_location_checked,
    apply_received_item,
    reduce_desired_state,
)
from ..domain.ids import ItemId, LocationId
from ..domain.seed_contract import SeedContract
from ..ports import APServerPort, ClockPort, GameRuntimePort, LoggerPort, PersistencePort


class MC3APClientService:
    """Top-level application service for the MC3 Archipelago client."""

    def __init__(
        self,
        ap: APServerPort,
        game: GameRuntimePort,
        store: PersistencePort,
        seed: SeedContract,
        logger: LoggerPort = None,
        clock: ClockPort = None,
    ):
        self._ap = ap
        self._game = game
        self._store = store
        self._seed = seed
        self._logger = logger or _NullLogger()
        self._clock = clock or _SystemClock()
        self._client_state: ClientState = ClientState()

    async def run(self):
        """Main client loop.  Blocks until disconnected."""
        self._logger.info("MC3AP client starting", seed=self._seed.seed_name)

        # Load persisted state
        self._client_state = await self._store.load_client_state()
        self._logger.info("Loaded persisted state", items=len(self._client_state.received_items))

        # Connect to AP server
        await self._ap.connect()
        self._logger.info("Connected to AP server")

        # Resync if needed
        await self._resync_items()

        # Connect to game runtime
        await self._game.connect()
        self._logger.info("Connected to game runtime")

        # Push initial desired state
        await self.reconcile_all()

        # Main event loop
        try:
            async for game_event in self._game.events():
                await self._handle_game_event(game_event)
        except asyncio.CancelledError:
            self._logger.info("Client shutting down")
        finally:
            await self._game.disconnect()
            await self._ap.disconnect()

    async def _handle_game_event(self, event: dict):
        """Dispatch a game event."""
        event_type = event.get("type", "")
        self._logger.debug("Game event", type=event_type)

        if event_type == "location_checked":
            location_id = event.get("location_id")
            if location_id:
                await self._on_location_checked(LocationId(str(location_id)))
        elif event_type == "goal_completed":
            await self._ap.send_goal()
            self._logger.info("Goal sent to AP server")

    async def _on_location_checked(self, location_id: LocationId):
        """Process a location that was checked in-game."""
        if location_id in self._client_state.checked_locations:
            return  # already known

        self._client_state = apply_location_checked(self._client_state, location_id)
        await self._store.save_client_state(self._client_state)
        await self._store.record_location_check(location_id, sent_to_ap=False)

        # Send to AP
        await self._ap.send_location_checks([location_id])
        await self._store.mark_checks_sent([location_id])
        self._logger.info("Check sent", location_id=location_id)

        # Recompute desired state (some gates unlock on checks)
        await self.reconcile_all()

    async def _resync_items(self):
        """Ensure item state matches AP server."""
        # TODO: implement full resync protocol:
        # 1. Compare received index with server
        # 2. If mismatch: send Sync + all known LocationChecks
        # 3. Receive catch-up items
        pass

    async def reconcile_all(self):
        """Full reconciliation: compute desired state, push to game, validate."""
        desired = reduce_desired_state(self._seed, self._client_state)
        await self._game.set_desired_state(desired)
        await self._store.record_desired_state(desired)
        self._logger.debug("Reconciled", state_hash=desired.state_hash)


# ── Null implementations ─────────────────────────────────────────────────────

class _NullLogger:
    def info(self, msg, **kw): pass
    def warning(self, msg, **kw): pass
    def error(self, msg, **kw): pass
    def debug(self, msg, **kw): pass


class _SystemClock:
    import datetime
    def now_iso(self) -> str:
        return self.datetime.datetime.now().isoformat()
    async def sleep(self, seconds: float):
        await asyncio.sleep(seconds)