from dataclasses import dataclass
from typing import List, Optional
import math
import numpy as np
import pandas as pd

from .candles import Candle

@dataclass
class Level:
    price: float
    type: str  # "high" | "low"
    timestamp: int            # ms (время самой экстремальной свечи i)
    datetime: str             # ISO8601 (UTC) этой свечи
    # новое: момент, когда уровень считается подтверждённым (после i + confirm_forward)
    confirmed_timestamp: int  = 0
    confirmed_datetime: str   = ""
    active: bool = True

class LiquidityLevels:
    """
    Локальные экстремумы с подтверждением через N будущих свечей (confirm_forward).
    - назад смотрим на `window` свечей
    - вперёд смотрим на `confirm_forward` свечей
    """
    def __init__(
        self,
        window: int = 6,                 # сколько свечей назад для локальности
        confirm_forward: int = 2,        # сколько свечей вперёд ждём подтверждение
        tick_size: Optional[float] = None,
        cluster_ticks: int = 2,
        touch_ticks: int = 1,
    ) -> None:
        assert window >= 1, "window must be >= 1"
        assert confirm_forward >= 1, "confirm_forward must be >= 1"
        self.window = window
        self.confirm_forward = confirm_forward
        self.tick_size = tick_size
        self.cluster_ticks = cluster_ticks
        self.touch_ticks = touch_ticks
        self.levels: List[Level] = []

    # ---------- Публичные API ----------

    def build(self, candles: List[Candle]) -> None:
        if not candles:
            self.levels = []
            return

        df = _candles_to_df(candles)
        H, L = df["High"].to_numpy(), df["Low"].to_numpy()
        n = len(df)
        w = self.window
        fwd = self.confirm_forward

        highs_idx, lows_idx = [], []

        # идём так, чтобы и back, и forward окна были внутри массива
        for i in range(w, n - fwd):
            # строгий локальный максимум: выше ближайших соседей,
            # выше макс. из последних w свечей (до i),
            # и не ниже макс. в ближайшие fwd свечей (после i) — чтобы пик устоял
            if _is_local_max_causal(H, i, w, fwd):
                highs_idx.append(i)
            if _is_local_min_causal(L, i, w, fwd):
                lows_idx.append(i)

        levels: List[Level] = []

        for i in highs_idx:
            ts_ms      = int(df.index[i].timestamp() * 1000)
            conf_ts_ms = int(df.index[i + fwd].timestamp() * 1000)
            price = _round_to_tick(H[i], self.tick_size)
            levels.append(Level(
                price=price, type="high",
                timestamp=ts_ms, datetime=df.index[i].isoformat(),
                confirmed_timestamp=conf_ts_ms, confirmed_datetime=df.index[i + fwd].isoformat(),
            ))

        for i in lows_idx:
            ts_ms      = int(df.index[i].timestamp() * 1000)
            conf_ts_ms = int(df.index[i + fwd].timestamp() * 1000)
            price = _round_to_tick(L[i], self.tick_size)
            levels.append(Level(
                price=price, type="low",
                timestamp=ts_ms, datetime=df.index[i].isoformat(),
                confirmed_timestamp=conf_ts_ms, confirmed_datetime=df.index[i + fwd].isoformat(),
            ))

        levels.sort(key=lambda x: x.timestamp)
        self.levels = _cluster_levels(levels, self.tick_size, self.cluster_ticks)

    def active_levels(self, timestamp_ms: int) -> List[Level]:
        """Активные уровни, подтверждённые строго ДО указанного времени."""
        return [l for l in self.levels if l.active and l.confirmed_timestamp < timestamp_ms]

    def prune(self, candle: Candle) -> None:
        """
        Снимаем уровни свечой только если уровень уже был подтверждён к моменту свечи.
        """
        hi = _round_to_tick(candle.high, self.tick_size)
        lo = _round_to_tick(candle.low, self.tick_size)
        ts = candle.timestamp

        for lvl in self.levels:
            # уровень должен быть подтверждён до текущей свечи
            if not lvl.active or lvl.confirmed_timestamp >= ts:
                continue

            tol = _ticks_to_abs(self.tick_size, self.touch_ticks)

            if lvl.type == "high":
                # прокол вверх
                if hi >= lvl.price - tol and lo <= lvl.price + tol:
                    lvl.active = False
            else:  # "low"
                # прокол вниз
                if lo <= lvl.price + tol and hi >= lvl.price - tol:
                    lvl.active = False

# ---------- Вспомогательные функции ----------

def _candles_to_df(candles: List[Candle]) -> pd.DataFrame:
    data = {
        "Open":  [c.open for c in candles],
        "High":  [c.high for c in candles],
        "Low":   [c.low for c in candles],
        "Close": [c.close for c in candles],
    }
    index = pd.to_datetime([c.timestamp for c in candles], unit="ms", utc=True)
    return pd.DataFrame(data, index=index)

def _round_to_tick(price: float, tick_size: Optional[float]) -> float:
    if not tick_size or tick_size <= 0:
        return float(price)
    return round(round(price / tick_size) * tick_size, _decimals(tick_size))

def _decimals(x: float) -> int:
    s = f"{x:.12f}".rstrip("0").rstrip(".")
    if "." in s:
        return len(s.split(".")[1])
    return 0

def _ticks_to_abs(tick_size: Optional[float], ticks: int) -> float:
    if not tick_size or tick_size <= 0:
        return 0.0
    return ticks * tick_size

def _is_local_max_causal(arr: np.ndarray, i: int, back_w: int, fwd_w: int) -> bool:
    # строго выше ближайших соседей (без плато)
    if not (arr[i] > arr[i - 1] and arr[i] > arr[i + 1]):
        return False
    # выше всего, что было в последних back_w свечах до i
    if arr[i] <= np.max(arr[i - back_w:i]):
        return False
    # и не ниже максимума на ближайших fwd_w свечах после i
    # (т.е. в окна [i+1, i+fwd_w] не появилось более высокой вершины)
    return arr[i] >= np.max(arr[i + 1:i + 1 + fwd_w])

def _is_local_min_causal(arr: np.ndarray, i: int, back_w: int, fwd_w: int) -> bool:
    if not (arr[i] < arr[i - 1] and arr[i] < arr[i + 1]):
        return False
    if arr[i] >= np.min(arr[i - back_w:i]):
        return False
    return arr[i] <= np.min(arr[i + 1:i + 1 + fwd_w])

def _cluster_levels(levels: List[Level], tick_size: Optional[float], cluster_ticks: int) -> List[Level]:
    if not levels or not tick_size or tick_size <= 0 or cluster_ticks <= 0:
        return levels
    tol = _ticks_to_abs(tick_size, cluster_ticks)
    result: List[Level] = []
    for lv in levels:
        if result and abs(result[-1].price - lv.price) <= tol and lv.type == result[-1].type:
            continue
        result.append(lv)
    return result
