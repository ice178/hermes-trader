from __future__ import annotations

from typing import Iterable, Protocol, Sequence

from .entities import Signal


class SignalRepository(Protocol):
    def add(self, signal: Signal) -> None:
        ...

    def add_many(self, signals: Iterable[Signal]) -> None:
        for signal in signals:
            self.add(signal)

    def list_recent(self, limit: int = 10) -> Sequence[Signal]:
        ...
