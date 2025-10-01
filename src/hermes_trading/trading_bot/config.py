from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .notifications.infrastructure.telegram import TelegramConfig


@dataclass
class DatabaseConfig:
    path: Path


@dataclass
class TradingBotConfig:
    database: DatabaseConfig
    telegram: TelegramConfig
