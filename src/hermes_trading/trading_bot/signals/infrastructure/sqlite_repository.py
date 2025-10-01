from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from ..domain.entities import Signal
from ..domain.repositories import SignalRepository
from ...levels.domain.entities import Level, LevelStatus, LevelType
from ...shared.domain.value_objects import PatternType, RiskReward


class SQLiteSignalRepository(SignalRepository):
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._ensure_schema()

    def add(self, signal: Signal) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO signals (
                    pattern, level_price, level_type, level_status, level_timestamp,
                    entry_price, stop_loss, take_profit, risk, reward, detected_at, symbol
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._serialize_signal(signal),
            )
            connection.commit()

    def add_many(self, signals: Iterable[Signal]) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.executemany(
                """
                INSERT INTO signals (
                    pattern, level_price, level_type, level_status, level_timestamp,
                    entry_price, stop_loss, take_profit, risk, reward, detected_at, symbol
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [self._serialize_signal(signal) for signal in signals],
            )
            connection.commit()

    def list_recent(self, limit: int = 10) -> Sequence[Signal]:
        with sqlite3.connect(self._database_path) as connection:
            cursor = connection.execute(
                """
                SELECT pattern, level_price, level_type, level_status, level_timestamp,
                       entry_price, stop_loss, take_profit, risk, reward, detected_at, symbol
                FROM signals
                ORDER BY detected_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()

        return [self._deserialize_signal(row) for row in rows]

    def _serialize_signal(self, signal: Signal) -> tuple:
        return (
            signal.pattern.value,
            signal.level.price,
            signal.level.level_type.value,
            signal.level.status.value,
            signal.level.candle_timestamp,
            signal.entry_price,
            signal.stop_loss,
            signal.take_profit,
            signal.risk_reward.risk,
            signal.risk_reward.reward,
            signal.detected_at.isoformat(),
            signal.symbol,
        )

    def _deserialize_signal(self, row: tuple) -> Signal:
        level = Level(
            price=row[1],
            level_type=LevelType(row[2]),
            status=LevelStatus(row[3]),
            candle_timestamp=row[4],
        )
        risk_reward = RiskReward(risk=row[8], reward=row[9])
        return Signal(
            pattern=PatternType(row[0]),
            level=level,
            entry_price=row[5],
            stop_loss=row[6],
            take_profit=row[7],
            risk_reward=risk_reward,
            detected_at=datetime.fromisoformat(row[10]),
            symbol=row[11],
        )

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL,
                    level_price REAL NOT NULL,
                    level_type TEXT NOT NULL,
                    level_status TEXT NOT NULL,
                    level_timestamp TEXT,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    risk REAL NOT NULL,
                    reward REAL NOT NULL,
                    detected_at TEXT NOT NULL,
                    symbol TEXT
                )
                """
            )
            connection.commit()
