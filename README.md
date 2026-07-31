# hermes-trading

Prototype trading bot framework.

## Features

- Exchange connector interface.
- Implementations for **Binance** and **BingX** using [CCXT](https://github.com/ccxt/ccxt).

## Development

Install dependencies and run tests:

```bash
pip install -e .
python3 -m pytest
```

## Backtesting

The repository now includes a historical backtest runner based on the same
signal logic used in `src/signals_bot.py`.

What it does:

- loads historical candles through an exchange connector;
- detects `pin_bar` and `railway_tracks` signals with the same
  volatility/volume filter as `signals_bot.py`;
- opens a virtual trade on the next candle `open`;
- sets stop distance from the current `trading.py` formula;
- tracks `PnL` in `R`, `MAE`, `MFE`, reached `R` steps (`0.25R`, `0.50R`, ...),
  time to reach each step, internal same-side/opposite-side signals, and
  `intrabar_conflict` cases.

Run example:

```bash
python3 src/run_strategy_backtest.py \
  --exchange binance \
  --symbols BTC/USDT ETH/USDT \
  --timeframes 15m 1h \
  --date-from 2025-01-01 \
  --date-to 2025-03-01 \
  --fetch-limit 1000 \
  --output-dir backtest_results
```

Optional strategy flags:

- `--patterns pin_bar railway_tracks`
- `--min-metric-increase-pct 10`
- `--take-step-r 0.25`
- `--allow-long`
- `--allow-short`
- `--no-export-trades`
- `--no-export-summary`

For longer historical backtests, `binance` is the safer default. BingX may reject
wide historical ranges and return no candles for broad date windows.

Artifacts written to `output-dir`:

- `trades.json`
- `trades.csv`
- `summary.json`
- `summary.md`

## Telegram notifications

Copy `.env.example` to `.env`, replace the placeholders, and load it into the
current shell. The application reads configuration from environment variables;
it does not parse `.env` itself.

```bash
cp .env.example .env
chmod 600 .env
set -a
. ./.env
set +a
```

```python
from hermes_trading.telegram import TelegramClient, TelegramConfig

client = TelegramClient(TelegramConfig.from_env())
client.send_text("Hermes trading is online.")
```

Never commit `.env` or paste credentials into source files. For a Linux server,
follow [the signal bot deployment guide](docs/server-deployment.md).
