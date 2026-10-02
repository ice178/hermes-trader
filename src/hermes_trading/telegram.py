"""Telegram Bot API helpers for simple message delivery."""

from __future__ import annotations

import json
from http.client import HTTPException
import os
import ssl
import urllib.error
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
ENV_BOT_TOKEN = "TELEGRAM_BOT_TOKEN"
ENV_CHAT_ID = "TELEGRAM_CHAT_ID"
ENV_SSL_INSECURE = "TELEGRAM_SSL_INSECURE"
ENV_CA_BUNDLE = "TELEGRAM_CA_BUNDLE"
SSL_INSECURE_VALUES = {"1", "true", "yes", "on"}


class TelegramError(RuntimeError):
    """Sanitized API/transport failure, without URLs, tokens or response bodies."""

    def __init__(self, code: int | None = None, retry_after: int = 0) -> None:
        self.code = code
        self.retry_after = retry_after
        super().__init__(f"Telegram request failed (code={code or 'transport'})")


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

    bot_token: str
    chat_id: str
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
    """Minimal Telegram Bot API client for delivery and command polling."""

    def __init__(self, config: TelegramConfig) -> None:
        self._config = config
        self._ssl_context = create_ssl_context(
            verify_ssl=config.verify_ssl,
            ca_bundle=config.ca_bundle,
        )

    def send_text(
        self, message: str, *, parse_mode: str | None = None,
        chat_id: int | str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": self._config.chat_id if chat_id is None else chat_id,
            "text": message,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return self._post("sendMessage", payload)

    def get_me(self) -> dict[str, Any]:
        result = self._post("getMe", {}).get("result")
        if (not isinstance(result, dict) or not isinstance(result.get("id"), int)
                or not isinstance(result.get("username"), str)):
            raise TelegramError()
        return result

    def get_updates(self, offset: int | None, *, timeout: int = 30) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout, "limit": 100,
            "allowed_updates": json.dumps(["message"]),
        }
        if offset is not None:
            payload["offset"] = offset
        result = self._post(
            "getUpdates", payload, timeout=timeout + self._config.timeout,
        ).get("result")
        if not isinstance(result, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("update_id"), int)
            for item in result
        ):
            raise TelegramError()
        return result

    def _post(
        self, method: str, payload: Mapping[str, Any], *, timeout: float | None = None,
    ) -> dict[str, Any]:
        data = urllib.parse.urlencode(payload).encode()
        url = f"{self._config.api_url}/bot{self._config.bot_token}/{method}"
        try:
            with urllib.request.urlopen(
                url, data=data,
                timeout=self._config.timeout if timeout is None else timeout,
                context=self._ssl_context,
            ) as response:  # noqa: S310
                body = response.read()
        except urllib.error.HTTPError as exc:
            retry_after = 0
            try:
                error = json.loads(exc.read())
                retry_after = max(0, int(error.get("parameters", {}).get("retry_after", 0)))
            except (ValueError, TypeError, AttributeError, OSError, HTTPException):
                pass
            finally:
                exc.close()
            raise TelegramError(exc.code, retry_after) from None
        except (OSError, urllib.error.URLError, ValueError, HTTPException):
            raise TelegramError() from None
        try:
            result = json.loads(body.decode("utf-8"))
            if not result.get("ok", False):
                raise TelegramError(
                    result.get("error_code"),
                    max(0, int(result.get("parameters", {}).get("retry_after", 0))),
                )
            return result
        except (ValueError, AttributeError, TypeError):
            raise TelegramError() from None


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
