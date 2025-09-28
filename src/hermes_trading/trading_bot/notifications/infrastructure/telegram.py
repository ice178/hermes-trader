from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from ...signals.domain.entities import Signal
from ..domain.interfaces import Messenger


@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str
    api_url: str = "https://api.telegram.org"


class TelegramMessenger(Messenger):
    """Telegram Bot API messenger implementation."""

    def __init__(self, config: TelegramConfig) -> None:
        self._config = config

    def send_signal(self, signal: Signal) -> None:
        message = self._format_signal(signal)
        self.send_text(message)

    def send_text(self, message: str) -> None:
        payload = {
            "chat_id": self._config.chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }
        self._post("sendMessage", payload)

    def _format_signal(self, signal: Signal) -> str:
        return (
            f"*{signal.pattern.value.title()}* signal on {signal.symbol or 'unknown'}\n"
            f"Entry: `{signal.entry_price}`\n"
            f"Stop: `{signal.stop_loss}`  Take profit: `{signal.take_profit}`\n"
            f"Risk/Reward: `{signal.risk_reward.ratio():.2f}`\n"
            f"Level: `{signal.level.price}` ({signal.level.level_type.value})"
        )

    def _post(self, method: str, payload: dict[str, Any]) -> None:
        url = f"{self._config.api_url}/bot{self._config.bot_token}/{method}"
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Telegram API error {response.status_code}: {response.text}"
            )
        data = response.json()
        if not data.get("ok", False):
            raise RuntimeError(
                f"Telegram API returned failure: {json.dumps(data)}"
            )
