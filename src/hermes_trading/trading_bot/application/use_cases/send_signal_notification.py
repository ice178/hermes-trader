from __future__ import annotations

from ...notifications.domain.interfaces import Messenger
from ...signals.domain.entities import Signal


class SendSignalNotification:
    """Use case for delivering signal notifications."""

    def __init__(self, messenger: Messenger) -> None:
        self._messenger = messenger

    def execute(self, signal: Signal) -> None:
        self._messenger.send_signal(signal)
