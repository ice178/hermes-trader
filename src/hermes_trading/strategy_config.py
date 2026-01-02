from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "strategy": {
        "timeframe": "1h",
        "research_mode": False,
        "executions_enabled": ["BASE_RR1"],
        "level_price_rounding": {"decimals": 2},
        "missing_indicator_policy": "skip",
        "filters": {
            "pin_bar_sell": {
                "enabled": False,
                "use_ema200": True,
                "ema200_near_atr": 0.1,
                "min_sl_atr": 0.8,
                "wick_body_ratio": 2.0,
                "close_location_max": 0.33,
                "max_distance_atr": 0.2,
                "use_sweep_filter": False,
                "min_sweep_atr": 0.05,
            }
        },
        "execution_params": {
            "time_stop_bars": 6,
            "be_trigger_R": 0.5,
            "be_offset_R": 0.0,
            "hybrid": {
                "tp1_R": 1.0,
                "tp2_R": 2.0,
                "tp1_size": 0.5,
                "tp2_size": 0.5,
                "move_stop_to_be": True,
            },
        },
        "commissions": {
            "enabled": False,
            "rate": 0.0004,
            "slippage_ticks": 0,
        },
    }
}


def load_strategy_config(path: Path | None) -> dict[str, Any]:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path is None or not path.exists():
        return config
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    return _deep_merge(config, loaded)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
