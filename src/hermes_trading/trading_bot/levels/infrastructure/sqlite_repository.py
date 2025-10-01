from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Sequence

from ..domain.entities import Level, LevelStatus, LevelType
from ..domain.repositories import LevelRepository


class SQLiteLevelRepository(LevelRepository):
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._ensure_schema()

    def add(self, level: Level) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO levels (price, type, status, candle_timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (
                    level.price,
                    level.level_type.value,
                    level.status.value,
                    level.candle_timestamp,
                ),
            )
            connection.commit()

    def add_many(self, levels: Iterable[Level]) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO levels (price, type, status, candle_timestamp)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        level.price,
                        level.level_type.value,
                        level.status.value,
                        level.candle_timestamp,
                    )
                    for level in levels
                ],
            )
            connection.commit()

    def list_active(self) -> Sequence[Level]:
        with sqlite3.connect(self._database_path) as connection:
            cursor = connection.execute(
                """
                SELECT price, type, status, candle_timestamp
                FROM levels
                WHERE status = ?
                ORDER BY price ASC
                """,
                (LevelStatus.ACTIVE.value,),
            )
            rows = cursor.fetchall()

        return [
            Level(
                price=row[0],
                level_type=LevelType(row[1]),
                status=LevelStatus(row[2]),
                candle_timestamp=row[3],
            )
            for row in rows
        ]

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS levels (
                    price REAL PRIMARY KEY,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    candle_timestamp TEXT
                )
                """
            )
            connection.commit()
