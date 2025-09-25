"""Price action pattern based trading signals."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, List, Literal

from ..candles import Candle, CandleBatch
from ..liquidity import Level
from .base import Signal, SignalMatch


@dataclass
class PriceActionSignal(Signal):
    """Detects price action patterns within a batch of candles."""

    def evaluate(self, candles: CandleBatch, levels: List[Level]) -> List[SignalMatch]:  # type: ignore[override]
        """Return pattern matches that align with qualified liquidity levels."""

        matches: List[SignalMatch] = []
        bars = candles.candles

        for idx, bar in enumerate(bars):
            touched_levels = [
                lvl
                for lvl in levels
                if self._level_is_actionable(lvl, bar)
            ]

            if not touched_levels:
                continue

            buy_levels = [lvl for lvl in touched_levels if lvl.type == "low"]
            sell_levels = [lvl for lvl in touched_levels if lvl.type == "high"]

            if buy_levels and self._is_buy_pin_bar(bar):
                matches.extend(
                    self._build_matches("pin_bar", "long", bar, buy_levels)
                )

            if sell_levels and self._is_sell_pin_bar(bar):
                matches.extend(
                    self._build_matches("pin_bar", "short", bar, sell_levels)
                )

            if idx > 0:
                prev = bars[idx - 1]

                if buy_levels and self._is_bullish_engulfing(prev, bar):
                    matches.extend(
                        self._build_matches("bullish_engulfing", "long", bar, buy_levels)
                    )

                if buy_levels and self._is_railway_tracks_long(prev, bar):
                    matches.extend(
                        self._build_matches("railway_tracks", "long", bar, buy_levels)
                    )

                if sell_levels and self._is_railway_tracks_short(prev, bar):
                    matches.extend(
                        self._build_matches("railway_tracks", "short", bar, sell_levels)
                    )

        return matches

    @staticmethod
    def _build_matches(
        pattern: str,
        direction: Literal["long", "short"],
        candle: Candle,
        levels: Iterable[Level],
    ) -> List[SignalMatch]:
        return [
            SignalMatch(
                pattern=pattern,
                direction=direction,
                candle=candle,
                level=level,
            )
            for level in levels
        ]

    @staticmethod
    def _level_is_actionable(level: Level, candle: Candle) -> bool:
        if not getattr(level, "active", True):
            return False

        confirmed_ts = getattr(level, "confirmed_timestamp", level.timestamp)
        if confirmed_ts >= candle.timestamp:
            return False

        if level.timestamp >= candle.timestamp:
            return False

        return candle.low <= level.price <= candle.high

    @staticmethod
    def _is_bullish_engulfing(prev: Candle, curr: Candle) -> bool:
        return (
            prev.close < prev.open
            and curr.close > curr.open
            and curr.close > prev.open
            and curr.open < prev.close
        )

    @staticmethod
    def _is_buy_pin_bar(c: Candle) -> bool:
        if c.open > c.close:
            return False

        body = abs(c.close - c.open)

        rng = c.high - c.low
        tail = min(c.open, c.close) - c.low
        head = c.high - max(c.open, c.close)
        return body < rng * 0.3 and tail > body * 2

    @staticmethod
    def _is_sell_pin_bar(c: Candle) -> bool:
        # Для медвежьего пин-бара тело должно быть "медвежьим" (закрытие ниже открытия)
        if c.open < c.close:
            return False

        body = abs(c.close - c.open)
        rng = c.high - c.low

        # Хвосты считаем зеркально
        tail = c.high - max(c.open, c.close)  # верхний хвост
        head = min(c.open, c.close) - c.low  # нижний хвост

        # Условие: тело маленькое, верхний хвост длиннее
        return body < rng * 0.3 and tail > body * 2  # and head * 2 < tail (если хочешь усилить фильтр)

    @staticmethod
    def _is_railway_tracks_long(prev: Candle, curr: Candle) -> bool:
        if prev.close >= prev.open:
            return False
        if curr.close <= curr.open:
            return False

        body1 = prev.open - prev.close
        body2 = curr.close - curr.open
        if body1 <= 0 or body2 <= 0:
            return False

        max_body = max(body1, body2)
        if max_body == 0:
            return False

        if abs(body1 - body2) / max_body >= 0.2:
            return False

        tolerance = max_body * 0.2
        if abs(curr.open - prev.close) > tolerance:
            return False
        if abs(curr.close - prev.open) > tolerance:
            return False

        return True

    @staticmethod
    def _is_railway_tracks_short(prev: Candle, curr: Candle) -> bool:
        if prev.close <= prev.open:
            return False
        if curr.close >= curr.open:
            return False

        body1 = prev.close - prev.open
        body2 = curr.open - curr.close
        if body1 <= 0 or body2 <= 0:
            return False

        max_body = max(body1, body2)
        if max_body == 0:
            return False

        if abs(body1 - body2) / max_body >= 0.2:
            return False

        tolerance = max_body * 0.2
        if abs(curr.open - prev.close) > tolerance:
            return False
        if abs(curr.close - prev.open) > tolerance:
            return False

        return True

    # -------- Pin bar (bull) --------

    def is_pin_bar_bull(self, c: Candle, **kwargs) -> bool:
        """Wrapper returning only True/False; kwargs forwarded to scorer."""
        return self._score_pin_bar_bull(c, **kwargs)

    @classmethod
    def _score_pin_bar_bull(
        cls,
        c: Candle,
        *,
        # мягкие гейты (быстрый отсев «совсем не похоже»)
        min_tail_to_range_gate: float = 0.35,
        min_tail_to_body_gate: float = 1.2,
        # веса
        w_tail_range: float = 40.0,
        w_tail_body: float = 25.0,
        w_head_small: float = 15.0,
        w_body_small: float = 10.0,
        w_body_position: float = 10.0,
        green_bonus: float = 5.0,
        # порог
        min_score: float = 60.0,
        return_debug: bool = False,
    ):
        h, l, o, cc = c.high, c.low, c.open, c.close
        rng = h - l
        if rng <= 0:
            return (False, {"reason": "zero_range"}) if return_debug else False

        body = abs(cc - o)
        tail = min(o, cc) - l          # нижняя тень
        head = h - max(o, cc)          # верхняя тень

        # нормированные метрики
        tail_r = tail / rng
        head_r = head / rng
        body_r = body / rng
        body_top_pos = (max(o, cc) - l) / rng  # 0..1 (хотим ближе к 1)

        # гейты
        if tail_r < min_tail_to_range_gate or (tail / (body + 1e-9)) < min_tail_to_body_gate:
            return (False, {"reason": "gates_fail", "tail_r": tail_r}) if return_debug else False

        # скоринг
        s_tail_range = w_tail_range * cls._linear_scale(tail_r, x0=0.30, x1=0.80)
        s_tail_body  = w_tail_body  * cls._linear_scale(tail / (body + 1e-9), x0=1.2, x1=3.0)
        s_head_small = w_head_small * cls._linear_scale(1.0 - cls._clamp(head_r, 0.10, 0.50), x0=1.0-0.50, x1=1.0-0.10)
        s_body_small = w_body_small * cls._linear_scale(1.0 - cls._clamp(body_r, 0.15, 0.50), x0=1.0-0.50, x1=1.0-0.15)
        s_body_pos   = w_body_position * cls._linear_scale(body_top_pos, x0=0.55, x1=0.85)

        score = s_tail_range + s_tail_body + s_head_small + s_body_small + s_body_pos
        if cc >= o:
            score += green_bonus

        is_pin = score >= min_score
        if return_debug:
            return is_pin, {
                "score": round(score, 2),
                "tail_r": round(tail_r, 3),
                "head_r": round(head_r, 3),
                "body_r": round(body_r, 3),
                "body_top_pos": round(body_top_pos, 3),
            }
        return is_pin

    # утилиты

    @staticmethod
    def _linear_scale(x: float, *, x0: float, x1: float) -> float:
        """Ниже x0 -> 0; выше x1 -> 1; между — линейно."""
        if x1 == x0:
            return 0.0
        if x <= x0:
            return 0.0
        if x >= x1:
            return 1.0
        return (x - x0) / (x1 - x0)

    @staticmethod
    def _clamp(x: float, a: float, b: float) -> float:
        return a if x < a else b if x > b else x
