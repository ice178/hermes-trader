from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from ..domain.entities import Candle
from ..domain.repositories import CandleRepository


class SQLiteCandleRepository(CandleRepository):
    """SQLite implementation of the candle repository."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._ensure_schema()

    def add(self, candle: Candle) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO candles (timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    candle.timestamp.isoformat(),
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                ),
            )
            connection.commit()

    def extend(self, candles: Iterable[Candle]) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.executemany(
                """
                INSERT INTO candles (timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        candle.timestamp.isoformat(),
                        candle.open,
                        candle.high,
                        candle.low,
                        candle.close,
                        candle.volume,
                    )
                    for candle in candles
                ],
            )
            connection.commit()

    def list(self, limit: int | None = None) -> Sequence[Candle]:
        query = "SELECT timestamp, open, high, low, close, volume FROM candles ORDER BY timestamp ASC"
        if limit is not None:
            query += " LIMIT ?"

        with sqlite3.connect(self._database_path) as connection:
            cursor = connection.execute(query, (limit,) if limit is not None else ())
            rows = cursor.fetchall()

        return [
            Candle(
                timestamp=datetime.fromisoformat(row[0]),
                open=row[1],
                high=row[2],
                low=row[3],
                close=row[4],
                volume=row[5],
            )
            for row in rows
        ]

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS candles (
                    timestamp TEXT PRIMARY KEY,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL
                )
                """
            )
            connection.commit()
