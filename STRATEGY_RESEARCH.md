# Strategy Research Layer

This document describes the research-oriented idea/execution pipeline, execution variants, filters, and trade record schema.

## Overview

The research layer separates **ideas** (signal intent) from **executions** (how the idea is traded). A single idea can be evaluated with multiple execution variants without changing the original production behavior.

By default (`research_mode: false`), the system keeps the existing BASE_RR1 behavior.

## Config

Configuration lives in `config/strategy.json` and is loaded by `src/hermes_trading/strategy_config.py`.

Key fields:

```json
{
  "strategy": {
    "research_mode": false,
    "executions_enabled": ["BASE_RR1"],
    "filters": {
      "pin_bar_sell": {
        "enabled": false,
        "use_ema200": true,
        "ema200_near_atr": 0.1,
        "min_sl_atr": 0.8,
        "wick_body_ratio": 2.0,
        "close_location_max": 0.33,
        "max_distance_atr": 0.2,
        "use_sweep_filter": false,
        "min_sweep_atr": 0.05
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
        "move_stop_to_be": true
      }
    }
  }
}
```

## Idea Model

Ideas are defined in `src/hermes_trading/idea.py`. The stable ID is generated as:

```
idea_id = sha1(
    f"{symbol}|{timeframe}|{pattern}|{side}|{signal_candle_time}|{rounded_level_price}"
).hexdigest()
```

`rounded_level_price` uses either `tick_size` or `decimals` configured under `level_price_rounding`.

## Execution Variants

* `BASE_RR1`: Existing behavior.
* `RR1_BE_TS`: Base RR1 with break-even move at `be_trigger_R` and time stop if no +0.3R after `time_stop_bars`.
* `RR2_FIXED`: Fixed 2R target with 1R stop.
* `RR2_HYBRID`: 50/50 partials at 1R and 2R, moving stop to break-even after TP1.

## Entry Filters (pin_bar SELL)

If enabled, the pin bar SELL filters enforce:

* EMA200 trend (`ema200_side == "below"`).
* ATR size filter (`sl_in_atr >= min_sl_atr`).
* Pin quality (upper wick, close location, touched + reclaimed level).
* Distance-to-level (`distance_to_level_atr <= max_distance_atr`).
* Optional sweep filter (`sweep_size_atr >= min_sweep_atr`).

If indicators are missing, `missing_indicator_policy` decides whether to skip or fail filters.

## Trade Record Fields

Each record includes:

* identifiers: `idea_id`, `execution_variant`, `execution_id`, `timeframe`, `signal_candle_time`
* risk/outcome: `risk_R`, `tp_R`, `realized_R`, `exit_reason`, `bars_in_trade`
* MFE/MAE in price and R, time-to-thresholds
* context features: ATR/EMA, candle geometry, distance-to-level, session/hour
* filter results and reasons

Records are stored in `trade_records.json` (when `research_mode` is enabled), with de-dup enforced on `(idea_id, execution_variant)`.
