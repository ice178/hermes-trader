"""Realtime trading bot orchestration."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, List, Sequence

from .candles import Candle, CandleBatch
from .connectors.base import ExchangeConnector
from .liquidity import Level, LiquidityLevels
from .signals.base import Signal, SignalMatch

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RealtimeBotConfig:
    """Runtime configuration for the realtime trading bot."""

    symbol: str
    interval: str
    database_path: Path = Path("trading.sqlite")
    poll_interval: float = 5.0
    history_limit: int = 500
    signal_batch_size: int = 10
    telegram_token: str | None = None
    telegram_chat_id: str | None = None

    def __post_init__(self) -> None:
        if self.signal_batch_size < 2:
            raise ValueError("signal_batch_size must be at least 2")


class SQLiteStorage:
    """SQLite-backed persistence for candles, levels, and signals."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._create_schema()

    def close(self) -> None:
        self._conn.close()

    def store_candle(self, symbol: str, interval: str, candle: Candle) -> bool:
        query = (
            "INSERT OR IGNORE INTO candles\n"
            "    (symbol, interval, timestamp, datetime, open, high, low, close)\n"
            "    VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        with self._conn:
            cur = self._conn.execute(
                query,
                (
                    symbol,
                    interval,
                    candle.timestamp,
                    candle.datetime,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                ),
            )
        return cur.rowcount > 0

    def last_candle_timestamp(self, symbol: str, interval: str) -> int | None:
        query = (
            "SELECT timestamp FROM candles\n"
            " WHERE symbol = ? AND interval = ?\n"
            " ORDER BY timestamp DESC\n"
            " LIMIT 1"
        )
        cur = self._conn.execute(query, (symbol, interval))
        row = cur.fetchone()
        return int(row[0]) if row else None

    def fetch_recent_candles(
        self, symbol: str, interval: str, limit: int
    ) -> List[Candle]:
        query = (
            "SELECT timestamp, datetime, open, high, low, close\n"
            "  FROM candles\n"
            " WHERE symbol = ? AND interval = ?\n"
            " ORDER BY timestamp DESC\n"
            " LIMIT ?"
        )
        cur = self._conn.execute(query, (symbol, interval, limit))
        rows = cur.fetchall()
        candles = [
            Candle(
                timestamp=int(ts),
                datetime=dt,
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
            )
            for ts, dt, open_, high, low, close in rows
        ]
        candles.reverse()
        return candles

    def store_level(self, symbol: str, interval: str, level: Level) -> bool:
        query = (
            "INSERT OR IGNORE INTO levels\n"
            "    (symbol, interval, price, type, timestamp, datetime,\n"
            "     confirmed_timestamp, confirmed_datetime, active)\n"
            "    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        with self._conn:
            cur = self._conn.execute(
                query,
                (
                    symbol,
                    interval,
                    level.price,
                    level.type,
                    level.timestamp,
                    level.datetime,
                    level.confirmed_timestamp,
                    level.confirmed_datetime,
                    int(level.active),
                ),
            )
        return cur.rowcount > 0

    def update_level_active(
        self,
        symbol: str,
        interval: str,
        level: Level,
    ) -> None:
        query = (
            "UPDATE levels SET active = ?\n"
            " WHERE symbol = ? AND interval = ?\n"
            "   AND timestamp = ? AND type = ?"
        )
        with self._conn:
            self._conn.execute(
                query,
                (int(level.active), symbol, interval, level.timestamp, level.type),
            )

    def store_signal(self, symbol: str, interval: str, match: SignalMatch) -> bool:
        payload = json.dumps(
            {
                "pattern": match.pattern,
                "direction": match.direction,
                "candle_timestamp": match.candle.timestamp,
                "level_timestamp": match.level.timestamp,
            }
        )
        query = (
            "INSERT OR IGNORE INTO signals\n"
            "    (symbol, interval, pattern, direction, candle_timestamp,\n"
            "     level_timestamp, payload, created_at)\n"
            "    VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))"
        )
        with self._conn:
            cur = self._conn.execute(
                query,
                (
                    symbol,
                    interval,
                    match.pattern,
                    match.direction,
                    match.candle.timestamp,
                    match.level.timestamp,
                    payload,
                ),
            )
        return cur.rowcount > 0

    def _create_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS candles (
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    datetime TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    PRIMARY KEY (symbol, interval, timestamp)
                );

                CREATE TABLE IF NOT EXISTS levels (
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    price REAL NOT NULL,
                    type TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    datetime TEXT NOT NULL,
                    confirmed_timestamp INTEGER NOT NULL,
                    confirmed_datetime TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    UNIQUE(symbol, interval, timestamp, type)
                );

                CREATE TABLE IF NOT EXISTS signals (
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    pattern TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    candle_timestamp INTEGER NOT NULL,
                    level_timestamp INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    UNIQUE(symbol, interval, pattern, candle_timestamp, level_timestamp)
                );
                """
            )


class TelegramNotifier:
    """Thin Telegram Bot API wrapper for signal broadcast."""

    def __init__(self, token: str | None, chat_id: str | None) -> None:
        self._token = token
        self._chat_id = chat_id

    def enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    def send_signal(self, match: SignalMatch, symbol: str, interval: str) -> None:
        if not self.enabled():
            return
        text = (
            f"Signal {match.pattern} ({match.direction}) on {symbol} {interval}\n"
            f"Level: {match.level.price} confirmed at {match.level.confirmed_datetime}\n"
            f"Candle close: {match.candle.close} at {match.candle.datetime}"
        )
        payload = urllib.parse.urlencode(
            {
                "chat_id": self._chat_id,
                "text": text,
            }
        ).encode()
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            with urllib.request.urlopen(url, data=payload, timeout=10) as resp:  # noqa: S310
                if resp.status >= 400:
                    logger.error("Telegram send failed: %s", resp.read())
        except Exception as exc:  # pragma: no cover - network failures depend on runtime
            logger.exception("Failed to notify Telegram: %s", exc)


class RealtimeTradingBot:
    """Polls the exchange for closed candles and orchestrates actions."""

    def __init__(
        self,
        connector: ExchangeConnector,
        storage: SQLiteStorage,
        config: RealtimeBotConfig,
        *,
        levels: LiquidityLevels | None = None,
        signals: Sequence[Signal] | None = None,
    ) -> None:
        self._connector = connector
        self._storage = storage
        self._config = config
        self._levels = levels or LiquidityLevels()
        self._signals = list(signals or []) or [PriceActionSignalAdapter()]
        self._notifier = TelegramNotifier(config.telegram_token, config.telegram_chat_id)
        self._recent: Deque[Candle] = deque(maxlen=config.history_limit)
        self._last_processed = self._storage.last_candle_timestamp(
            config.symbol, config.interval
        )
        self._timeframe_ms = timeframe_to_milliseconds(config.interval)

    def run_forever(self) -> None:
        logger.info(
            "Starting realtime bot for %s %s", self._config.symbol, self._config.interval
        )
        self._load_recent_history()
        while True:
            try:
                candle = self._fetch_latest_closed_candle()
            except Exception:
                logger.exception("Failed to fetch candles")
                time.sleep(self._config.poll_interval)
                continue

            if candle is None or (
                self._last_processed is not None and candle.timestamp <= self._last_processed
            ):
                time.sleep(self._config.poll_interval)
                continue

            try:
                self._process_candle(candle)
                self._last_processed = candle.timestamp
            except Exception:
                logger.exception("Error while processing candle")

            time.sleep(self._config.poll_interval)

    def run_once(self) -> None:
        """Process a single update; useful for testing."""
        candle = self._fetch_latest_closed_candle()
        if candle is None:
            return
        if self._last_processed is not None and candle.timestamp <= self._last_processed:
            return
        self._process_candle(candle)
        self._last_processed = candle.timestamp

    def _load_recent_history(self) -> None:
        cached = self._storage.fetch_recent_candles(
            self._config.symbol, self._config.interval, self._config.history_limit
        )
        for candle in cached:
            self._recent.append(candle)
        if self._recent:
            logger.info("Loaded %s candles from cache", len(self._recent))

    def _fetch_latest_closed_candle(self) -> Candle | None:
        batch = self._connector.get_klines(
            self._config.symbol,
            self._config.interval,
        )
        candles = batch.candles
        if not candles:
            return None
        latest = candles[-1]
        now_ms = int(time.time() * 1000)
        if now_ms - latest.timestamp < self._timeframe_ms and len(candles) > 1:
            return candles[-2]
        if now_ms - latest.timestamp < self._timeframe_ms:
            return None
        return latest

    def _process_candle(self, candle: Candle) -> None:
        if not self._storage.store_candle(self._config.symbol, self._config.interval, candle):
            logger.debug("Candle %s already processed", candle.timestamp)
            return

        self._recent.append(candle)
        if len(self._recent) < self._levels.window + self._levels.confirm_forward + 1:
            logger.debug("Not enough candles for level detection yet")
            return

        history = list(self._recent)
        self._levels.build(history)

        # track activation state changes after pruning with the new candle
        before = {(lvl.timestamp, lvl.type): lvl.active for lvl in self._levels.levels}
        self._levels.prune(candle)

        for lvl in self._levels.levels:
            inserted = self._storage.store_level(self._config.symbol, self._config.interval, lvl)
            if inserted:
                logger.info(
                    "New level %s at %s confirmed at %s",
                    lvl.type,
                    lvl.price,
                    lvl.confirmed_datetime,
                )
            if before.get((lvl.timestamp, lvl.type)) != lvl.active:
                self._storage.update_level_active(
                    self._config.symbol,
                    self._config.interval,
                    lvl,
                )

        active_levels = self._levels.active_levels(candle.timestamp)
        if len(history) < self._config.signal_batch_size:
            return
        batch_candles = history[-max(self._config.signal_batch_size, 10) :]
        if len(batch_candles) < 10:
            return
        signal_batch = CandleBatch(batch_candles[-10:])

        for signal in self._signals:
            for match in signal.evaluate(signal_batch, active_levels):
                if self._storage.store_signal(
                    self._config.symbol,
                    self._config.interval,
                    match,
                ):
                    logger.info(
                        "Signal %s %s for candle %s", match.pattern, match.direction, match.candle.timestamp
                    )
                    self._notifier.send_signal(match, self._config.symbol, self._config.interval)


class PriceActionSignalAdapter(Signal):
    """Wraps the default price action detector as a Signal implementation."""

    def __init__(self) -> None:
        from .signals.price_action import PriceActionSignal

        self._delegate = PriceActionSignal()

    def evaluate(self, candles: CandleBatch, levels: List[Level]) -> Sequence[SignalMatch]:
        return self._delegate.evaluate(candles, levels)


def timeframe_to_milliseconds(interval: str) -> int:
    units = {
        "s": 1000,
        "m": 60_000,
        "h": 3_600_000,
        "d": 86_400_000,
        "w": 604_800_000,
    }
    suffix = interval[-1]
    if suffix not in units:
        raise ValueError(f"Unsupported interval: {interval}")
    value = int(interval[:-1])
    return value * units[suffix]
