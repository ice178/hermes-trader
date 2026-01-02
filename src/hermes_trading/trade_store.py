from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TradeStore:
    path: Path | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    _keys: set[tuple[str, str]] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.path and self.path.exists():
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                self.records = data
                for record in data:
                    idea_id = record.get("idea_id")
                    variant = record.get("execution_variant")
                    if idea_id and variant:
                        self._keys.add((idea_id, variant))

    def has_record(self, idea_id: str, execution_variant: str) -> bool:
        return (idea_id, execution_variant) in self._keys

    def add_record(self, record: dict[str, Any]) -> bool:
        idea_id = record.get("idea_id")
        execution_variant = record.get("execution_variant")
        if not idea_id or not execution_variant:
            self.records.append(record)
            return True
        key = (idea_id, execution_variant)
        if key in self._keys:
            return False
        self._keys.add(key)
        self.records.append(record)
        return True

    def save(self) -> None:
        if not self.path:
            return
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(self.records, handle, ensure_ascii=False, indent=2)
