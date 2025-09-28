from __future__ import annotations

from pathlib import Path

from .application.use_cases.process_new_candle import ProcessNewCandle
from .application.use_cases.send_signal_notification import SendSignalNotification
from .candles.infrastructure.sqlite_repository import SQLiteCandleRepository
from .config import TradingBotConfig
from .levels.infrastructure.simple_detector import SwingHighLowLevelDetector
from .levels.infrastructure.sqlite_repository import SQLiteLevelRepository
from .notifications.infrastructure.telegram import TelegramMessenger
from .signals.infrastructure.simple_detector import PriceActionSignalDetector
from .signals.infrastructure.simple_risk_calculator import BasicRiskCalculator
from .signals.infrastructure.sqlite_repository import SQLiteSignalRepository


def build_process_new_candle_use_case(
    config: TradingBotConfig,
) -> ProcessNewCandle:
    database_path = Path(config.database.path)

    candle_repository = SQLiteCandleRepository(database_path)
    level_repository = SQLiteLevelRepository(database_path)
    signal_repository = SQLiteSignalRepository(database_path)

    level_detector = SwingHighLowLevelDetector()
    risk_calculator = BasicRiskCalculator()
    signal_detector = PriceActionSignalDetector(risk_calculator=risk_calculator)

    messenger = TelegramMessenger(config.telegram)
    send_signal_notification = SendSignalNotification(messenger)

    return ProcessNewCandle(
        candle_repository=candle_repository,
        level_repository=level_repository,
        signal_repository=signal_repository,
        level_detector=level_detector,
        signal_detector=signal_detector,
        send_signal_notification=send_signal_notification,
    )
