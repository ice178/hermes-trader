from __future__ import annotations

from typing import Protocol

from ...signals.domain.entities import Signal


class Messenger(Protocol):
    """Interface for messaging platforms."""

    def send_signal(self, signal: Signal) -> None:
        ...

    def send_text(self, message: str) -> None:
        ...
