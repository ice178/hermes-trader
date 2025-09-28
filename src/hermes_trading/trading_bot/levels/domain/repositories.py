from __future__ import annotations

from typing import Iterable, Protocol, Sequence

from .entities import Level


class LevelRepository(Protocol):
    def add(self, level: Level) -> None:
        ...

    def add_many(self, levels: Iterable[Level]) -> None:
        for level in levels:
            self.add(level)

    def list_active(self) -> Sequence[Level]:
        ...
