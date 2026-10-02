"""SQLite persistence for manual areas and restart-safe command processing."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, Iterator

from .manual_levels import PriceArea, area_sort_key, price_text

SCHEMA_VERSION = 1
BUSY_TIMEOUT_SECONDS = 5
OFFSET_MAX_AGE_SECONDS = 6 * 24 * 60 * 60

SCHEMA = (
    """CREATE TABLE manual_price_areas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exchange TEXT NOT NULL, symbol TEXT NOT NULL,
        shape TEXT NOT NULL CHECK(shape IN ('point', 'zone')),
        lower_price TEXT NOT NULL CHECK(valid_price(lower_price)),
        upper_price TEXT NOT NULL CHECK(valid_price(upper_price)),
        side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
        kind TEXT NOT NULL, source_timeframe TEXT NOT NULL,
        comment TEXT NOT NULL CHECK(length(comment) <= 500),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'deleted')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT,
        CHECK((shape = 'point' AND lower_price = upper_price) OR
              (shape = 'zone' AND price_compare(lower_price, upper_price) < 0))
    )""",
    """CREATE UNIQUE INDEX unique_active_area ON manual_price_areas
        (exchange, symbol, side, shape, lower_price, upper_price, kind,
         source_timeframe) WHERE status = 'active'""",
    """CREATE INDEX active_market ON manual_price_areas
        (exchange, symbol, side, status)""",
    "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE processed_updates (
        update_id INTEGER NOT NULL, fingerprint TEXT NOT NULL,
        PRIMARY KEY (update_id, fingerprint))""",
    """CREATE TABLE replies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL, text TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending', 'attempted', 'sent', 'failed'))
    )""",
)


def _valid_price(value: str) -> int:
    try:
        return int(price_text(value) == value)
    except (ValueError, TypeError):
        return 0


def _price_compare(left: str, right: str) -> int:
    try:
        a, b = Decimal(left), Decimal(right)
        return (a > b) - (a < b)
    except ArithmeticError:
        return 0


def _area(row: sqlite3.Row) -> PriceArea:
    return PriceArea(**{
        key: Decimal(row[key]) if key in {"lower_price", "upper_price"} else row[key]
        for key in PriceArea.__dataclass_fields__
    })


class LevelStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    @contextmanager
    def connection(self, *, create: bool = False) -> Iterator[sqlite3.Connection]:
        mode = "rwc" if create else "rw"
        conn = sqlite3.connect(
            f"{self.path.as_uri()}?mode={mode}", uri=True,
            timeout=BUSY_TIMEOUT_SECONDS, isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.create_function("valid_price", 1, _valid_price, deterministic=True)
        conn.create_function("price_compare", 2, _price_compare, deterministic=True)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def initialize(self) -> None:
        """Create or migrate the schema explicitly, before polling starts."""
        with self.connection(create=True) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            try:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, SCHEMA_VERSION):
                    raise ValueError("Unsupported levels database schema version")
                if version == 0:
                    for statement in SCHEMA:
                        conn.execute(statement)
                    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @staticmethod
    def list_active(
        conn: sqlite3.Connection, *, symbol: str | None = None,
        exchange: str | None = None,
    ) -> list[PriceArea]:
        rows = conn.execute(
            """SELECT * FROM manual_price_areas WHERE status='active'
               AND (? IS NULL OR symbol=?) AND (? IS NULL OR exchange=?)""",
            (symbol, symbol, exchange, exchange),
        ).fetchall()
        return sorted((_area(row) for row in rows), key=area_sort_key)

    def active_areas(self, exchange: str, symbol: str) -> list[PriceArea]:
        with self.connection() as conn:
            if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                raise sqlite3.DatabaseError("Unsupported levels database schema")
            return self.list_active(conn, exchange=exchange, symbol=symbol)

    @staticmethod
    def add(
        conn: sqlite3.Connection, *, exchange: str, symbol: str, side: str,
        shape: str, lower_price: str, upper_price: str, kind: str,
        source_timeframe: str, comment: str,
    ) -> tuple[PriceArea, bool]:
        lower, upper = price_text(lower_price), price_text(upper_price)
        now = datetime.now(timezone.utc).isoformat()
        key = (exchange, symbol, side, shape, lower, upper, kind, source_timeframe)
        cursor = conn.execute(
            """INSERT INTO manual_price_areas
               (exchange, symbol, side, shape, lower_price, upper_price, kind,
                source_timeframe, comment, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT DO NOTHING""", (*key, comment, now, now),
        )
        row = conn.execute(
            """SELECT * FROM manual_price_areas WHERE exchange=? AND symbol=?
               AND side=? AND shape=? AND lower_price=? AND upper_price=?
               AND kind=? AND source_timeframe=? AND status='active'""", key,
        ).fetchone()
        return _area(row), cursor.rowcount == 1

    @staticmethod
    def delete(
        conn: sqlite3.Connection, *, exchange: str, symbol: str,
        shape: str, lower_price: str, upper_price: str,
    ) -> list[PriceArea]:
        key = (exchange, symbol, shape, price_text(lower_price), price_text(upper_price))
        clause = ("exchange=? AND symbol=? AND shape=? AND lower_price=? "
                  "AND upper_price=? AND status='active'")
        rows = conn.execute("SELECT * FROM manual_price_areas WHERE " + clause, key)
        areas = sorted((_area(row) for row in rows), key=area_sort_key)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE manual_price_areas SET status='deleted', updated_at=?, "
            "deleted_at=? WHERE " + clause, (now, now, *key),
        )
        return areas

    @staticmethod
    def _set(conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute("INSERT INTO metadata VALUES (?, ?) ON CONFLICT(key) "
                     "DO UPDATE SET value=excluded.value", (key, value))

    def bind_bot(self, bot_id: int) -> None:
        with self.transaction() as conn:
            row = conn.execute("SELECT value FROM metadata WHERE key='bot_id'").fetchone()
            if row and row[0] != str(bot_id):
                raise ValueError("Levels database belongs to a different Telegram bot")
            self._set(conn, "bot_id", str(bot_id))

    def offset(self, *, now: float | None = None) -> int | None:
        with self.connection() as conn:
            state = dict(conn.execute("SELECT key, value FROM metadata"))
        now = time.time() if now is None else now
        # Telegram may randomize update IDs after a week without new updates.
        if now - float(state.get("received_at", "0")) >= OFFSET_MAX_AGE_SECONDS:
            return None
        return int(state["offset"]) if "offset" in state else None

    def process_update(
        self, update: dict[str, Any],
        handler: Callable[[sqlite3.Connection, dict[str, Any]], list[tuple[int, str]]],
    ) -> bool:
        message = update.get("message")
        identity = update
        if isinstance(message, dict):
            # User names and other incidental fields can change on redelivery.
            # Message identity also distinguishes IDs randomized after idle time.
            identity = {"message_id": message.get("message_id"),
                        "chat_id": message.get("chat", {}).get("id"),
                        "date": message.get("date")}
        fingerprint = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        update_id = update["update_id"]
        with self.transaction() as conn:
            inserted = conn.execute(
                "INSERT OR IGNORE INTO processed_updates VALUES (?, ?)",
                (update_id, fingerprint),
            ).rowcount
            if inserted:
                replies = handler(conn, update)
                conn.executemany("INSERT INTO replies (chat_id, text) VALUES (?, ?)", replies)
            self._set(conn, "offset", str(update_id + 1))
            self._set(conn, "received_at", str(time.time()))
        return bool(inserted)

    def claim_reply(self) -> tuple[int, int, str] | None:
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT id, chat_id, text FROM replies WHERE status='pending' ORDER BY id LIMIT 1"
            ).fetchone()
            if row:
                conn.execute("UPDATE replies SET status='attempted' WHERE id=?", (row[0],))
                return tuple(row)
        return None

    def finish_reply(self, reply_id: int, status: str) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE replies SET status=? WHERE id=?", (status, reply_id))

    def uncertain_reply_count(self) -> int:
        with self.connection() as conn:
            return conn.execute(
                "SELECT count(*) FROM replies WHERE status='attempted'"
            ).fetchone()[0]
