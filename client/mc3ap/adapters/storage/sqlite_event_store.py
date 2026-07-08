"""SQLite event store — persists all AP state with proper indexing.

Schema per Section 14.1 of the design doc.
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ....domain.ids import ItemId, LocationId
from ....domain.reducer import ClientState, DesiredGameState


class SqliteEventStore:
    """SQLite-backed persistence for the MC3AP client."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    async def initialize(self):
        """Create tables if they don't exist."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS received_items (
                ap_index INTEGER PRIMARY KEY,
                item_id INTEGER NOT NULL,
                location_id INTEGER,
                sender INTEGER,
                flags INTEGER,
                received_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS location_checks (
                location_id TEXT PRIMARY KEY,
                source_event_id TEXT,
                first_seen_at TEXT NOT NULL,
                sent_to_ap INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS desired_state_snapshots (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                state_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                blob BLOB NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runtime_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload BLOB NOT NULL,
                received_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ap_connection_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        self._conn.commit()

    async def load_client_state(self) -> ClientState:
        """Reconstruct ClientState from persisted data."""
        cursor = self._conn.execute(
            "SELECT ap_index, item_id FROM received_items ORDER BY ap_index"
        )
        received_items = {}
        item_instances: dict[ItemId, set[int]] = {}
        for ap_index, item_id in cursor.fetchall():
            received_items[ap_index] = ItemId(item_id)
            item_instances.setdefault(ItemId(item_id), set()).add(ap_index)

        cursor = self._conn.execute("SELECT location_id FROM location_checks")
        checked = frozenset(LocationId(row[0]) for row in cursor.fetchall())

        cursor = self._conn.execute(
            "SELECT value FROM ap_connection_state WHERE key = 'goal_sent_to_ap'"
        )
        goal_row = cursor.fetchone()
        goal_sent = goal_row is not None and goal_row[0] == "1"

        cursor = self._conn.execute(
            "SELECT value FROM ap_connection_state WHERE key = 'total_ap_money_applied'"
        )
        money_row = cursor.fetchone()
        total_money = int(money_row[0]) if money_row else 0

        return ClientState(
            received_items=received_items,
            item_instance_ids={k: frozenset(v) for k, v in item_instances.items()},
            checked_locations=checked,
            goal_sent_to_ap=goal_sent,
            total_ap_money_applied=total_money,
        )

    async def save_client_state(self, state: ClientState):
        """Full save of client state (usually incremental via record_* methods)."""
        pass  # Incremental updates happen via record_* methods

    async def record_received_item(self, ap_index: int, item_id: ItemId):
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO received_items (ap_index, item_id, received_at) VALUES (?, ?, ?)",
            (ap_index, int(item_id), now),
        )
        self._conn.commit()

    async def record_location_check(self, location_id: LocationId, sent_to_ap: bool = False):
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR IGNORE INTO location_checks (location_id, first_seen_at, sent_to_ap) VALUES (?, ?, ?)",
            (str(location_id), now, int(sent_to_ap)),
        )
        self._conn.commit()

    async def record_desired_state(self, state: DesiredGameState):
        now = datetime.now(timezone.utc).isoformat()
        blob = json.dumps({
            "allowed_cities": sorted(state.allowed_cities),
            "allowed_vehicles": sorted(state.allowed_vehicles),
            "total_ap_money": state.total_ap_money,
        }).encode()
        self._conn.execute(
            "INSERT INTO desired_state_snapshots (state_hash, created_at, blob) VALUES (?, ?, ?)",
            (state.state_hash, now, blob),
        )
        self._conn.commit()

    async def record_game_event(self, event_type: str, payload: bytes):
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO runtime_events (event_type, payload, received_at) VALUES (?, ?, ?)",
            (event_type, payload, now),
        )
        self._conn.commit()

    async def get_unsent_checks(self) -> List[LocationId]:
        cursor = self._conn.execute(
            "SELECT location_id FROM location_checks WHERE sent_to_ap = 0"
        )
        return [LocationId(row[0]) for row in cursor.fetchall()]

    async def mark_checks_sent(self, location_ids: List[LocationId]):
        self._conn.executemany(
            "UPDATE location_checks SET sent_to_ap = 1 WHERE location_id = ?",
            [(str(lid),) for lid in location_ids],
        )
        self._conn.commit()

    async def get_ap_connection_state(self, key: str) -> Optional[str]:
        cursor = self._conn.execute(
            "SELECT value FROM ap_connection_state WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    async def set_ap_connection_state(self, key: str, value: str):
        self._conn.execute(
            "INSERT OR REPLACE INTO ap_connection_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()