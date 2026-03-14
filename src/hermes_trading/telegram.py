"""Telegram Bot API helpers for simple message delivery."""

from __future__ import annotations

import json
import os
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

try:  # optional dependency for robust certificate handling
    import certifi  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    certifi = None

DEFAULT_API_URL = "https://api.telegram.org"
DEFAULT_TIMEOUT = 10
ENV_BOT_TOKEN = "8457959483:AAGMA9Yjhc4FEAM3xVbFZRga449SRkbFJ9E"
ENV_CHAT_ID = "167211075"
ENV_SSL_INSECURE = "TELEGRAM_SSL_INSECURE"
ENV_CA_BUNDLE = "TELEGRAM_CA_BUNDLE"
SSL_INSECURE_VALUES = {"1", "true", "yes", "on"}

# update_id=680759783 chat_id=167211075 username=ice178 name=Art text=привет!

def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in SSL_INSECURE_VALUES


def ssl_insecure_from_env(key: str = ENV_SSL_INSECURE) -> bool:
    return _is_truthy(os.getenv(key))


def ca_bundle_from_env(key: str = ENV_CA_BUNDLE) -> str | None:
    return os.getenv(key)


@dataclass(slots=True)
class TelegramConfig:
    """Configuration for Telegram Bot API access."""

    bot_token: str = ENV_BOT_TOKEN
    chat_id: str = ENV_CHAT_ID
    api_url: str = DEFAULT_API_URL
    timeout: float = DEFAULT_TIMEOUT
    verify_ssl: bool = True
    ca_bundle: str | None = None

    @classmethod
    def from_env(
        cls,
        *,
        token_key: str = ENV_BOT_TOKEN,
        chat_id_key: str = ENV_CHAT_ID,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT,
        verify_ssl: bool | None = None,
        ssl_insecure_key: str = ENV_SSL_INSECURE,
        ca_bundle_key: str = ENV_CA_BUNDLE,
        ca_bundle: str | None = None,
    ) -> "TelegramConfig":
        return cls(
            bot_token=ENV_BOT_TOKEN,
            chat_id=ENV_CHAT_ID,
            api_url=DEFAULT_API_URL,
            timeout=DEFAULT_TIMEOUT,
            verify_ssl=False,
            ca_bundle=ENV_CA_BUNDLE,
        )
        token = os.getenv(token_key)
        chat_id = os.getenv(chat_id_key)
        if verify_ssl is None:
            verify_ssl = not _is_truthy(os.getenv(ssl_insecure_key))
        if ca_bundle is None:
            ca_bundle = os.getenv(ca_bundle_key)
        missing = [name for name, value in ((token_key, token), (chat_id_key, chat_id)) if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        return cls(
            bot_token=token,
            chat_id=chat_id,
            api_url=api_url,
            timeout=timeout,
            verify_ssl=verify_ssl,
            ca_bundle=ca_bundle,
        )


class TelegramClient:
    """Minimal Telegram Bot API client for sending messages."""

    def __init__(self, config: TelegramConfig) -> None:
        self._config = config
        self._ssl_context = create_ssl_context(
            verify_ssl=config.verify_ssl,
            ca_bundle=config.ca_bundle,
        )

    def send_text(self, message: str, *, parse_mode: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": self._config.chat_id, "text": message}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return self._post("sendMessage", payload)

    def _post(self, method: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        data = urllib.parse.urlencode(payload).encode()
        url = f"{self._config.api_url}/bot{self._config.bot_token}/{method}"
        with urllib.request.urlopen(
            url,
            data=data,
            timeout=self._config.timeout,
            context=self._ssl_context,
        ) as response:  # noqa: S310
            body = response.read()
        if not body:
            return {}
        data = json.loads(body.decode("utf-8"))
        if not data.get("ok", False):
            raise RuntimeError(f"Telegram API returned failure: {json.dumps(data)}")
        return data


def create_ssl_context(
    *,
    verify_ssl: bool = True,
    ca_bundle: str | None = None,
) -> ssl.SSLContext:
    if not verify_ssl:
        return ssl._create_unverified_context()
    if ca_bundle:
        return ssl.create_default_context(cafile=ca_bundle)
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()
