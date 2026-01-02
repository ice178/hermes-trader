from __future__ import annotations

from typing import Any

from .features import EntryFeatures


def apply_pin_bar_sell_filters(
    features: EntryFeatures,
    *,
    config: dict[str, Any],
    missing_indicator_policy: str,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    def _handle_missing(name: str) -> None:
        if missing_indicator_policy == "fail":
            reasons.append(f"missing_{name}")

    if config.get("use_ema200", True):
        if features.ema200_side is None:
            _handle_missing("ema200")
        elif features.ema200_side != "below":
            reasons.append("ema200_not_below")

    min_sl_atr = config.get("min_sl_atr", 0.8)
    if features.sl_in_atr is None:
        _handle_missing("atr")
    elif features.sl_in_atr < min_sl_atr:
        reasons.append("sl_below_min_atr")

    wick_body_ratio = config.get("wick_body_ratio", 2.0)
    close_location_max = config.get("close_location_max", 0.33)

    if features.upper_wick < wick_body_ratio * features.body_size:
        reasons.append("upper_wick_too_small")
    if features.close_location is None:
        _handle_missing("close_location")
    elif features.close_location > close_location_max:
        reasons.append("close_location_too_high")
    if not features.touched_level:
        reasons.append("level_not_touched")
    if not features.reclaimed_level:
        reasons.append("level_not_reclaimed")

    max_distance_atr = config.get("max_distance_atr", 0.2)
    if features.distance_to_level_atr is None:
        _handle_missing("distance_to_level")
    elif features.distance_to_level_atr > max_distance_atr:
        reasons.append("distance_to_level_too_far")

    if config.get("use_sweep_filter", False):
        min_sweep_atr = config.get("min_sweep_atr", 0.05)
        if features.sweep_size_atr is None:
            _handle_missing("sweep_size")
        elif features.sweep_size_atr < min_sweep_atr:
            reasons.append("sweep_too_small")

    return len(reasons) == 0, reasons
