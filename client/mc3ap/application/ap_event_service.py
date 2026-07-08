"""AP event processing service."""

from ..domain.ids import ItemId, LocationId
from ..domain.reducer import ClientState, apply_received_item
from ..ports import LoggerPort, PersistencePort


class APEventService:
    """Handles Archipelago protocol events and translates to domain operations."""

    def __init__(self, store: PersistencePort, logger: LoggerPort = None):
        self._store = store
        self._logger = logger

    async def handle_received_items(
        self,
        client_state: ClientState,
        index: int,
        items: list[dict],
    ) -> ClientState:
        """Process a ReceivedItems packet.

        index == 0 → full inventory reset.
        index > 0 → append items.
        """
        if index == 0:
            # Full inventory replacement
            received = {}
            for item in items:
                item_id = ItemId(item["item"])
                idx = item.get("index", len(received))
                received[idx] = item_id
            self._logger.info("Full inventory reset", item_count=len(received))
            from ..domain.reducer import apply_full_inventory_reset
            return apply_full_inventory_reset(received)

        # Append items
        for item in items:
            item_id = ItemId(item["item"])
            ap_index = index
            client_state = apply_received_item(client_state, ap_index, item_id)
            await self._store.record_received_item(ap_index, item_id)
            self._logger.debug("Item received", item_id=item_id, index=ap_index)
            index += 1

        await self._store.save_client_state(client_state)
        return client_state