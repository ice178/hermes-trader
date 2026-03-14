"""Fetch recent Telegram updates to discover chat IDs."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import urllib.parse
import urllib.request
from typing import Any

try:  # optional dependency for robust certificate handling
    import certifi  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    certifi = None

DEFAULT_API_URL = "https://api.telegram.org"
DEFAULT_TIMEOUT = 10
ENV_BOT_TOKEN = "8457959483:AAGMA9Yjhc4FEAM3xVbFZRga449SRkbFJ9E"
ENV_CHAT_ID = "TELEGRAM_CHAT_ID"
ENV_SSL_INSECURE = "TELEGRAM_SSL_INSECURE"
ENV_CA_BUNDLE = "TELEGRAM_CA_BUNDLE"
SSL_INSECURE_VALUES = {"1", "true", "yes", "on"}


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in SSL_INSECURE_VALUES


def _create_ssl_context(
    *,
    verify_ssl: bool,
    ca_bundle: str | None,
) -> ssl.SSLContext:
    if not verify_ssl:
        return ssl._create_unverified_context()
    if ca_bundle:
        return ssl.create_default_context(cafile=ca_bundle)
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def _request_updates(
    token: str,
    *,
    api_url: str,
    timeout: float,
    offset: int | None,
    limit: int,
    ssl_context: ssl.SSLContext,
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": limit}
    if offset is not None:
        params["offset"] = offset
    query = urllib.parse.urlencode(params)
    url = f"{api_url}/bot{token}/getUpdates?{query}"
    with urllib.request.urlopen(url, timeout=timeout, context=ssl_context) as response:  # noqa: S310
        body = response.read()
    if not body:
        return {}
    data = json.loads(body.decode("utf-8"))
    if not data.get("ok", False):
        raise RuntimeError(f"Telegram API returned failure: {json.dumps(data)}")
    return data


def _format_chat(update: dict[str, Any]) -> str:
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat", {})
    user = message.get("from", {})
    text = message.get("text") or ""
    return (
        "chat_id={chat_id} username={username} name={name} text={text}".format(
            chat_id=chat.get("id", "unknown"),
            username=user.get("username") or "unknown",
            name=(user.get("first_name") or "unknown"),
            text=text.replace("\n", " "),
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print chat IDs from recent Telegram bot updates."
    )
    parser.add_argument(
        "--token",
        default=os.getenv(ENV_BOT_TOKEN),
        help=f"Bot token (default: ${ENV_BOT_TOKEN}).",
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Telegram API base URL.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Request timeout.")
    parser.add_argument("--offset", type=int, default=None, help="Update offset.")
    parser.add_argument("--limit", type=int, default=10, help="Number of updates to fetch.")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable SSL verification (not recommended).",
    )
    parser.add_argument(
        "--ca-bundle",
        default=None,
        help=f"Path to CA bundle (default: ${ENV_CA_BUNDLE}).",
    )
    args = parser.parse_args(argv)
    args.token = "8457959483:AAGMA9Yjhc4FEAM3xVbFZRga449SRkbFJ9E"

    if not args.token:
        raise ValueError(f"Missing bot token. Set ${ENV_BOT_TOKEN} or pass --token.")

    ca_bundle = args.ca_bundle or os.getenv(ENV_CA_BUNDLE)
    verify_ssl = not args.insecure and not _is_truthy(os.getenv(ENV_SSL_INSECURE))
    ssl_context = _create_ssl_context(verify_ssl=verify_ssl, ca_bundle=ca_bundle)

    data = _request_updates(
        args.token,
        api_url=args.api_url,
        timeout=args.timeout,
        offset=args.offset,
        limit=args.limit,
        ssl_context=ssl_context,
    )
    updates = data.get("result", [])
    if not updates:
        print("No updates found. Send a message to the bot first.")
        return 0

    for update in updates:
        update_id = update.get("update_id")
        print(f"update_id={update_id} {_format_chat(update)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
