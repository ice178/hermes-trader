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
- detects `pin_bar` and `railway_tracks` signals with a configurable
  volatility/volume filter;
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

The historical backtest keeps this metric filter for strategy analysis. The
live Telegram bot also filters by default: both volume and volatility (candle
high minus low) must be at least 10% above each of the two reference candles.
Set `SIGNAL_METRIC_FILTER_ENABLED=0` to disable this gate explicitly; metric
context is then shown only for metrics that pass.

For longer historical backtests, `binance` is the safer default. BingX may reject
wide historical ranges and return no candles for broad date windows.

Artifacts written to `output-dir`:

- `trades.json`
- `trades.csv`
- `summary.json`
- `summary.md`

## Manual historical pattern search

Use the separate manual scanner to find patterns over a date range without
simulating trades. The production scanner and its timer keep their schedule.

```bash
python3 src/scan_signals.py \
  --exchange binance \
  --symbols BTC/USDT ETH/USDT \
  --timeframes 15m 1h \
  --date-from 2026-09-01 \
  --date-to 2026-09-07
```

The range applies to the **close time of the final pattern candle**. A date-only
end includes that entire local day (the example ends at September 8, 00:00 in
Barcelona). Naive dates/times default to **Europe/Madrid (Barcelona time)**,
with daylight saving handled automatically. For example,
`--date-from '2026-09-01 08:00' --date-to '2026-09-01 12:00'` uses Barcelona time.
Use `--timezone UTC` for UTC input, or provide ISO offsets / `Z` explicitly;
explicit offsets are always honored. Exact datetime bounds are start-inclusive
and end-exclusive. Nonexistent or ambiguous local times at a DST transition
require an explicit offset. Printed signal times use Europe/Madrid, as live
notifications do. The separate backtest runner retains its UTC defaults.

All live pattern types are scanned, including engulfing and inside bars.
Earlier candles are fetched for context; open candles are excluded. Each
symbol/timeframe reports loaded, in-range, evaluated and matching counts.
Missing/nonconsecutive context is skipped and reported with exit status 1;
zero patterns after a successful scan returns 0. Exchange history limits still
apply, so these results cover the candles the exchange supplied.

Output goes to the terminal and requires no Telegram credentials. Add
`--send-telegram` to send messages labeled **Historical scan** using the existing
Telegram environment configuration. Repeating an explicit send can repeat
historical notifications.

To test levels saved through the Telegram daemon, load the same environment
and add `--check-levels`:

```bash
set -a
source .env
set +a

python3 src/scan_signals.py \
  --exchange bingx \
  --symbols BTC/USDT \
  --timeframes 15m \
  --date-from '2026-09-24 09:00' \
  --date-to '2026-09-24 12:00' \
  --check-levels \
  --no-metric-filter
```

Replace the example interval with the period you want to inspect. This reads
active areas from the existing `LEVELS_DB_PATH` at scan start. It prints the
areas, each pattern's wick-inclusive price range, matching IDs or `no match`,
and a final `Patterns matching current levels: N/M` count. Market and direction
must match: a BingX buy area only matches a BingX LONG signal for the same ticker.
The source timeframe is informational, so a level marked on 15m can also match
another signal timeframe. The check does not delete areas or filter out signals.

This is a **test of current areas against historical candles**, not a replay of
which areas existed at that time. Without `--check-levels`, no area database is
read. The daemon may keep running during the test. `--send-telegram` also works
with level testing and labels these messages accordingly. Missing/incompatible
databases fail before market requests; start/configure the daemon to initialize
the database rather than creating an empty file yourself.

Defaults use BingX and the live scanner's symbols/timeframes. For a wider
historical range, Binance may be necessary if BingX rejects the query. Use
`--metric-filter` or `--no-metric-filter` to override
`SIGNAL_METRIC_FILTER_ENABLED` (on by default), and `--fetch-limit` to set
the request page size (1–1000). Calendar-month candles (`1M`) are not supported
by this fixed-duration historical loader. Run `python3 src/scan_signals.py --help`
for the full argument list.

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

With the default `SIGNAL_METRIC_FILTER_ENABLED=1`, both volume and volatility
must be at least 10% above each of the two reference candles before a live
signal is sent. Missing or blank configuration also enables the filter.
Set it to `0` to make metrics informational only. An existing `.env` or server
environment value of `0` must be changed to `1` when upgrading; deployments do
not overwrite configuration.

```python
from hermes_trading.telegram import TelegramClient, TelegramConfig

client = TelegramClient(TelegramConfig.from_env())
client.send_text("Hermes trading is online.")
```

Never commit `.env` or paste credentials into source files. For a Linux server,
follow [the signal bot deployment guide](docs/server-deployment.md).

## Manual levels and zones

The optional continuous Telegram listener accepts authorized commands to add,
list, and soft-delete manual price levels and zones in SQLite. Live signals
include matching areas across the complete pattern, including candle wicks.
The scanner continues to use its existing systemd timer.

See [commands, daemon setup, and backup](docs/manual-levels.md). Configure
`TELEGRAM_ALLOWED_USER_IDS` and `LEVELS_DB_PATH`, then run
`python3 src/levels_bot.py` locally or install `hermes-levels-bot.service` on the
server. Keep one polling listener per bot token. An empty `LEVELS_DB_PATH`
preserves notifications without manual-area annotations.
