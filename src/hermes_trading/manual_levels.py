"""Manual point levels and price zones, independent of liquidity levels."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Iterable

from .signals import SignalMatch

TIMEFRAMES = (
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h",
    "12h", "1d", "3d", "1w", "1M",
)
POINT_KINDS = ("day_high", "day_low", "level", "mirror")
ZONE_KINDS = ("imbalance",)
MAX_COMMENT_LENGTH = 500
MAX_PRICE_DIGITS = 24
PRICE_PATTERN = re.compile(
    rf"[0-9]{{1,{MAX_PRICE_DIGITS}}}(?:\.[0-9]{{1,{MAX_PRICE_DIGITS}}})?\Z"
)
KIND_LABELS = {
    "day_high": "Day high", "day_low": "Day low", "level": "Level",
    "mirror": "Mirror", "imbalance": "Imbalance",
}


def price_text(value: str | Decimal) -> str:
    """Validate a plain positive decimal and return its exact canonical text."""
    raw = str(value)
    if not PRICE_PATTERN.fullmatch(raw) or Decimal(raw) <= 0:
        raise ValueError("Price must be positive, with at most 24 digits on each "
                         "side of the decimal point (no exponent or comma).")
    whole, _, fraction = raw.partition(".")
    whole = whole.lstrip("0") or "0"
    fraction = fraction.rstrip("0")
    return whole + ("." + fraction if fraction else "")


def normalize_timeframe(value: str) -> str:
    result = value if value == "1M" else value.lower()
    if result not in TIMEFRAMES:
        raise ValueError("Timeframe must be one of: " + ", ".join(TIMEFRAMES))
    return result


@dataclass(frozen=True)
class PriceArea:
    id: int
    exchange: str
    symbol: str
    shape: str
    lower_price: Decimal
    upper_price: Decimal
    side: str
    kind: str
    source_timeframe: str
    comment: str
    status: str


def area_sort_key(area: PriceArea) -> tuple:
    return (area.exchange, area.symbol, area.lower_price, area.upper_price, area.id)


def describe_area(area: PriceArea) -> str:
    bounds = format(area.lower_price, "f")
    if area.shape == "zone":
        bounds += "–" + format(area.upper_price, "f")
    label = KIND_LABELS.get(area.kind, area.kind)
    note = f" — {area.comment}" if area.comment else ""
    return (f"#{area.id} {area.exchange} {area.symbol}: {bounds}, {area.side}, "
            f"{label} [source: {area.source_timeframe}]{note}")


def matching_areas(
    match: SignalMatch, exchange: str, areas: Iterable[PriceArea],
) -> list[PriceArea]:
    candles = match.pattern_candles
    if not candles:
        if match.pattern != "pin_bar":
            raise ValueError("Multi-candle signal is missing constituent candles")
        candles = (match.candle,)
    low = min(Decimal(str(candle.low)) for candle in candles)
    high = max(Decimal(str(candle.high)) for candle in candles)
    side = {"long": "buy", "short": "sell"}[match.direction]
    return sorted(
        (area for area in areas
         if area.exchange == exchange.lower()
         and area.symbol == match.candle.symbol.upper()
         and area.status == "active" and area.side == side
         and high >= area.lower_price and low <= area.upper_price),
        key=area_sort_key,
    )
