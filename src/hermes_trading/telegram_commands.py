"""Parse and authorize Telegram commands without performing network I/O."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import sqlite3
from typing import Any, Mapping, Sequence

from .level_store import LevelStore
from .manual_levels import (
    MAX_COMMENT_LENGTH, POINT_KINDS, TIMEFRAMES, ZONE_KINDS,
    describe_area, normalize_timeframe, price_text,
)
from .scanner_config import SCAN_MARKETS

MESSAGE_LIMIT = 3500


def text_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def split_records(header: str, records: Sequence[str]) -> list[str]:
    """Keep records intact and repeat the header in each transport-safe part."""
    messages: list[str] = []
    current = header
    for record in records:
        if text_units(header + "\n" + record) > MESSAGE_LIMIT:
            raise ValueError("A record exceeds the Telegram message limit")
        if text_units(current + "\n" + record) > MESSAGE_LIMIT:
            messages.append(current)
            current = header
        current += "\n" + record
    messages.append(current)
    return messages


@dataclass(frozen=True)
class Command:
    name: str
    symbol: str | None = None
    exchange: str = ""
    shape: str = "point"
    side: str = ""
    timeframe: str = ""
    kind: str = ""
    prices: tuple[str, ...] = ()
    comment: str = ""


def help_text(markets: Mapping[str, Sequence[str]]) -> str:
    return (
        "/levels_add SYMBOL EXCHANGE buy|sell TIMEFRAME KIND PRICE [PRICE ...] | comment\n"
        "/zone_add SYMBOL EXCHANGE buy|sell TIMEFRAME imbalance LOW HIGH | comment\n"
        "/levels [SYMBOL]\n"
        "/level_delete SYMBOL EXCHANGE PRICE\n"
        "/zone_delete SYMBOL EXCHANGE LOW HIGH\n"
        "/help\n"
        "Point kinds: " + ", ".join(POINT_KINDS) + "\n"
        "Timeframes: " + ", ".join(TIMEFRAMES) + " (1m = minute; 1M = month)\n"
        "Prices: positive plain decimals, max 24 digits before/after the dot.\n"
        "Comments: optional, max 500 characters. Delete affects all exact matches.\n"
        "Markets: " + "; ".join(
            exchange + " " + ", ".join(symbols) for exchange, symbols in markets.items()
        )
    )


def parse_command(
    text: str, *, bot_username: str,
    markets: Mapping[str, Sequence[str]] = SCAN_MARKETS,
) -> Command | None:
    body, separator, comment = text.strip().partition("|")
    tokens = body.split()
    if not tokens or not tokens[0].startswith("/"):
        return None
    name, at, suffix = tokens[0].partition("@")
    if at and suffix.lower() != bot_username.lower():
        return None
    args = tokens[1:]
    name = name.lower()
    known = {"/help", "/start", "/levels", "/levels_add", "/zone_add",
             "/level_delete", "/zone_delete"}
    if name not in known:
        raise ValueError("Unknown command. Use /help.")
    if name in {"/help", "/start", "/levels"}:
        if separator or len(args) > (1 if name == "/levels" else 0):
            raise ValueError("Invalid arguments. Use /help.")
        symbol = args[0].upper() if args else None
        if symbol and not any(symbol in symbols for symbols in markets.values()):
            raise ValueError("Unsupported symbol. Use /help for available markets.")
        return Command(name=name, symbol=symbol)

    adding = name in {"/levels_add", "/zone_add"}
    shape = "zone" if name.startswith("/zone") else "point"
    expected = 6 if adding else (4 if shape == "zone" else 3)
    if ((adding and len(args) < expected)
            or (not adding and len(args) != expected)
            or (name == "/zone_add" and len(args) != 7)):
        raise ValueError("Invalid argument count. Use /help.")
    if separator and not adding:
        raise ValueError("Comments are supported only by add commands.")
    symbol, exchange = args[0].upper(), args[1].lower()
    if exchange not in markets or symbol not in markets[exchange]:
        raise ValueError("Unsupported exchange/symbol pair. Use /help for markets.")
    comment = comment.strip()
    if len(comment) > MAX_COMMENT_LENGTH or "\x00" in comment:
        raise ValueError("Comment must contain at most 500 characters and no NUL.")
    try:
        comment.encode("utf-16-le")
    except UnicodeEncodeError:
        raise ValueError("Comment contains invalid Unicode.") from None
    if adding:
        side = args[2].lower()
        if side not in {"buy", "sell"}:
            raise ValueError("Side must be buy or sell.")
        timeframe = normalize_timeframe(args[3])
        kind = args[4].lower()
        if kind not in (ZONE_KINDS if shape == "zone" else POINT_KINDS):
            raise ValueError("Unsupported kind for this shape. Use /help.")
        raw_prices = args[5:]
    else:
        side = timeframe = kind = ""
        raw_prices = args[2:]
    prices = tuple(price_text(price) for price in raw_prices)
    if shape == "zone" and Decimal(prices[0]) >= Decimal(prices[1]):
        raise ValueError("Zone lower bound must be less than its upper bound.")
    return Command(name, symbol, exchange, shape, side, timeframe, kind, prices, comment)


class CommandHandler:
    def __init__(
        self, allowed_user_ids: frozenset[int], bot_username: str,
        markets: Mapping[str, Sequence[str]] = SCAN_MARKETS,
    ) -> None:
        self.allowed_user_ids = allowed_user_ids
        self.bot_username = bot_username
        self.markets = markets

    def handle(
        self, conn: sqlite3.Connection, update: dict[str, Any],
    ) -> list[tuple[int, str]]:
        message = update.get("message")
        if not isinstance(message, dict):
            return []
        sender = message.get("from")
        if not isinstance(sender, dict):
            return []
        if (sender.get("id") not in self.allowed_user_ids or sender.get("is_bot")
                or message.get("sender_chat")):
            return []
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text")
        if not isinstance(chat_id, int) or not isinstance(text, str):
            return []
        try:
            command = parse_command(text, bot_username=self.bot_username, markets=self.markets)
        except ValueError as exc:
            return [(chat_id, str(exc))]
        if command is None:
            return []
        return [(chat_id, text) for text in self.execute(conn, command)]

    def execute(self, conn: sqlite3.Connection, command: Command) -> list[str]:
        if command.name in {"/help", "/start"}:
            return [help_text(self.markets)]
        if command.name == "/levels":
            areas = LevelStore.list_active(conn, symbol=command.symbol)
            header = f"Active areas: {len(areas)}"
            return split_records(header, [describe_area(area) for area in areas])
        if command.name in {"/level_delete", "/zone_delete"}:
            areas = LevelStore.delete(
                conn, exchange=command.exchange, symbol=command.symbol,
                shape=command.shape, lower_price=command.prices[0],
                upper_price=command.prices[-1],
            )
            header = f"Deleted {len(areas)} areas."
            if len(areas) > 1:
                header += " Multiple exact matches were deleted:"
            return split_records(header, [describe_area(area) for area in areas])
        records = []
        created = duplicates = 0
        bounds = ([(command.prices[0], command.prices[1])] if command.shape == "zone"
                  else [(price, price) for price in command.prices])
        for lower, upper in bounds:
            area, added = LevelStore.add(
                conn, exchange=command.exchange, symbol=command.symbol,
                shape=command.shape, lower_price=lower, upper_price=upper,
                side=command.side, kind=command.kind,
                source_timeframe=command.timeframe, comment=command.comment,
            )
            created += int(added)
            duplicates += int(not added)
            records.append(("Added " if added else "Already active ") + describe_area(area))
        return split_records(f"Added {created}; already active {duplicates}.", records)
