from __future__ import annotations

from typing import Iterable, Sequence

from ...candles.domain.entities import Candle
from ...candles.domain.repositories import CandleRepository
from ...levels.domain.repositories import LevelRepository
from ...levels.domain.services import LevelDetector
from ...signals.domain.repositories import SignalRepository
from ...signals.domain.services import SignalDetector
from ...signals.domain.entities import Signal
from .send_signal_notification import SendSignalNotification


class ProcessNewCandle:
    """Main orchestrator for handling new candle events."""

    def __init__(
        self,
        candle_repository: CandleRepository,
        level_repository: LevelRepository,
        signal_repository: SignalRepository,
        level_detector: LevelDetector,
        signal_detector: SignalDetector,
        send_signal_notification: SendSignalNotification,
    ) -> None:
        self._candle_repository = candle_repository
        self._level_repository = level_repository
        self._signal_repository = signal_repository
        self._level_detector = level_detector
        self._signal_detector = signal_detector
        self._send_signal_notification = send_signal_notification

    def execute(self, candle: Candle) -> Sequence[Signal]:
        self._candle_repository.add(candle)
        candles = self._candle_repository.list()
        levels = self._level_detector.detect(candles)
        self._level_repository.add_many(levels)

        signals = self._signal_detector.detect(candles, levels)
        self._signal_repository.add_many(signals)
        self._notify(signals)
        return signals

    def _notify(self, signals: Iterable[Signal]) -> None:
        for signal in signals:
            self._send_signal_notification.execute(signal)
