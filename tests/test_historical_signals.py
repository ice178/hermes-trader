from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from hermes_trading.candles import Candle
from hermes_trading.level_store import LevelStore
from hermes_trading.historical_signals import (
    HistoricalScan, ScanRange, evaluate_historical_patterns, scan_historical_patterns,
)
from hermes_trading.time_utils import madrid_datetime_from_timestamp_ms
import scan_signals

STEP = 15 * 60 * 1000
BASE = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def candles():
    result = [Candle(
        timestamp=BASE + i * STEP,
        datetime=madrid_datetime_from_timestamp_ms(BASE + i * STEP),
        open=100, high=101, low=99, close=100, volume=100,
        symbol="BTC/USDT", timeframe="15m",
    ) for i in range(6)]
    result[3].open, result[3].high, result[3].low, result[3].close = 95, 97, 85, 96
    result[3].volume = 1
    return result


def test_dates_include_end_day_and_normalize_timezone():
    one_day = ScanRange.parse("2026-01-01", "2026-01-01")
    assert one_day.start_ms == BASE - 60 * 60 * 1000
    assert one_day.end_ms == BASE + 23 * 60 * 60 * 1000
    utc_day = ScanRange.parse("2026-01-01", "2026-01-01", timezone_name="UTC")
    assert utc_day.start_ms == BASE
    assert utc_day.end_ms == BASE + 24 * 60 * 60 * 1000
    exact = ScanRange.parse("2026-01-01T01:00:00+01:00", "2026-01-01T01:15:00+01:00")
    assert exact == ScanRange(BASE, BASE + STEP)
    assert ScanRange.parse("2026-01-01T00:00:00Z", "2026-01-01T00:15:00Z") == exact


@pytest.mark.parametrize("date,hours", [("2026-03-29", 23), ("2026-10-25", 25)])
def test_local_date_only_ranges_follow_dst_day_length(date, hours):
    window = ScanRange.parse(date, date)
    assert window.end_ms - window.start_ms == hours * 60 * 60 * 1000


def test_summer_input_uses_barcelona_offset():
    window = ScanRange.parse("2026-09-25T09:00", "2026-09-25T10:00")
    assert window == ScanRange.parse("2026-09-25T07:00Z", "2026-09-25T08:00Z")


@pytest.mark.parametrize("start,end,reason", [
    ("2026-03-29T02:30", "2026-03-29T04:00", "does not exist"),
    ("2026-10-25T02:30", "2026-10-25T04:00", "ambiguous"),
])
def test_dst_gaps_and_folds_require_explicit_offset(start, end, reason):
    with pytest.raises(ValueError, match=reason):
        ScanRange.parse(start, end)


def test_explicit_offsets_distinguish_repeated_local_hour():
    window = ScanRange.parse("2026-10-25T02:30+02:00", "2026-10-25T02:30+01:00")
    assert window.end_ms - window.start_ms == 60 * 60 * 1000


@pytest.mark.parametrize("start,end", [
    ("invalid", "2026-01-01"), ("2026-01-02", "2026-01-01"),
    ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
])
def test_bad_date_ranges_are_rejected(start, end):
    with pytest.raises(ValueError):
        ScanRange.parse(start, end)


def test_close_boundaries_and_old_signals_use_warmup_context():
    result = evaluate_historical_patterns(
        candles(), "15m", ScanRange(BASE + 4 * STEP, BASE + 5 * STEP),
        now_ms=BASE + 100 * STEP,
    )
    assert result.eligible_candles == result.evaluated_candles == 1
    assert len(result.signals) == 1
    assert result.signals[0].match.candle.timestamp == BASE + 3 * STEP
    assert result.signals[0].match.pattern == "pin_bar"
    excluded = evaluate_historical_patterns(
        candles(), "15m", ScanRange(BASE + 3 * STEP, BASE + 4 * STEP),
        now_ms=BASE + 100 * STEP,
    )
    assert not excluded.signals


def test_open_candle_is_not_evaluated_until_exact_close():
    window = ScanRange(BASE + 4 * STEP, BASE + 5 * STEP)
    for delay, expected in [(-1, 0), (0, 1), (1, 1)]:
        result = evaluate_historical_patterns(candles(), "15m", window,
                                             now_ms=BASE + 4 * STEP + delay)
        assert len(result.signals) == expected


def test_metrics_are_informational_unless_enabled():
    window = ScanRange(BASE + 4 * STEP, BASE + 5 * STEP)
    unfiltered = evaluate_historical_patterns(candles(), "15m", window,
                                              now_ms=BASE + 10 * STEP)
    filtered = evaluate_historical_patterns(candles(), "15m", window,
                                            now_ms=BASE + 10 * STEP,
                                            metric_filter_enabled=True)
    assert len(unfiltered.signals) == 1 and not filtered.signals


@pytest.mark.parametrize("pattern,ohlc", [
    ("railway_tracks", [(100, 101, 99, 100), (110, 115, 98, 100), (100, 111, 99, 110)]),
    ("inside_bar", [(100, 101, 99, 100), (110, 120, 90, 100), (100.5, 111, 99, 109.5)]),
    ("buy_engulfing", [(110, 130, 98, 106), (105, 106, 99, 100), (99, 112, 98, 111)]),
    ("sell_engulfing", [(100, 130, 90, 104), (105, 110, 99, 109), (110, 112, 98, 99)]),
])
def test_historical_scan_includes_all_live_pattern_types(pattern, ohlc):
    bars = candles()
    for bar, (open_, high, low, close) in zip(bars[1:4], ohlc):
        bar.open, bar.high, bar.low, bar.close = open_, high, low, close
    result = evaluate_historical_patterns(
        bars, "15m", ScanRange(BASE + 4 * STEP, BASE + 5 * STEP),
        now_ms=BASE + 100 * STEP,
    )
    assert pattern in {signal.match.pattern for signal in result.signals}


def test_gaps_are_skipped_and_duplicate_unsorted_candles_are_deduplicated():
    bars = candles()
    window = ScanRange(BASE + 4 * STEP, BASE + 5 * STEP)
    result = evaluate_historical_patterns(list(reversed(bars)) + [bars[3]], "15m", window,
                                         now_ms=BASE + 10 * STEP)
    assert len(result.signals) == 1 and result.loaded_candles == 6
    del bars[1]
    result = evaluate_historical_patterns(bars, "15m", window, now_ms=BASE + 10 * STEP)
    assert result.eligible_candles == 1 and result.evaluated_candles == 0
    assert not result.signals


def test_loader_fetches_warmup_and_paginates_overlapping_pages():
    bars = candles()
    rows = [[bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume] for bar in bars]
    connector = Mock()
    connector.client.fetch_ohlcv.side_effect = [rows[:2], rows[1:4], rows[3:5]]
    result = scan_historical_patterns(
        connector, "BTC/USDT", "15m", ScanRange(BASE + 4 * STEP, BASE + 5 * STEP),
        now_ms=BASE + 10 * STEP, fetch_limit=2,
    )
    assert len(result.signals) == 1 and result.loaded_candles == 5
    assert connector.client.fetch_ohlcv.call_count == 3
    assert connector.client.fetch_ohlcv.call_args_list[0].kwargs["since"] == BASE
    assert connector.client.fetch_ohlcv.call_args_list[1].kwargs["since"] == BASE + 2 * STEP


def test_loader_clamps_end_to_now_and_returns_empty_data(monkeypatch):
    loader = Mock(return_value=[])
    monkeypatch.setattr("hermes_trading.historical_signals.fetch_historical_candles", loader)
    now_ms = BASE + 5 * STEP
    result = scan_historical_patterns(Mock(), "BTC/USDT", "15m",
                                     ScanRange(BASE + 4 * STEP, BASE + 100 * STEP),
                                     now_ms=now_ms)
    assert result == HistoricalScan(0, 0, 0, ())
    end = datetime.fromisoformat(loader.call_args.args[4])
    assert int(end.timestamp() * 1000) == now_ms + 1


CLI_ARGS = ["--date-from", "2026-01-01", "--date-to", "2026-01-01",
            "--symbols", "BTC/USDT", "--timeframes", "15m"]


@pytest.fixture
def fake_scan(monkeypatch):
    connector = Mock()
    monkeypatch.setattr(scan_signals, "create_connector", connector)
    result = evaluate_historical_patterns(
        candles(), "15m", ScanRange(BASE + 4 * STEP, BASE + 5 * STEP),
        now_ms=BASE + 10 * STEP,
    )
    scanner = Mock(return_value=result)
    monkeypatch.setattr(scan_signals, "scan_historical_patterns", scanner)
    monkeypatch.delenv("SIGNAL_METRIC_FILTER_ENABLED", raising=False)
    return scanner, connector


def test_cli_defaults_to_terminal_without_telegram_credentials(fake_scan, monkeypatch, capsys):
    monkeypatch.setattr(scan_signals.TelegramConfig, "from_env",
                        Mock(side_effect=AssertionError("must not read Telegram config")))
    assert scan_signals.main(CLI_ARGS) == 0
    output = capsys.readouterr().out
    assert "LONG pin_bar" in output and "Patterns found: 1" in output
    assert "2026-01-01T02:00:00+01:00" in output
    assert fake_scan[0].call_args.kwargs["metric_filter_enabled"] is True


def test_cli_telegram_delivery_is_explicit_and_labeled(fake_scan, monkeypatch):
    client = Mock()
    monkeypatch.setattr(scan_signals.TelegramConfig, "from_env", Mock(return_value=object()))
    monkeypatch.setattr(scan_signals, "TelegramClient", Mock(return_value=client))
    assert scan_signals.main(CLI_ARGS + ["--send-telegram"]) == 0
    client.send_text.assert_called_once()
    assert client.send_text.call_args.args[0].startswith("<b>Historical scan</b>")
    assert client.send_text.call_args.kwargs == {"parse_mode": "HTML"}


@pytest.mark.parametrize("args", [
    [], ["--date-from", "2026-01-01"],
    ["--date-from", "bad", "--date-to", "2026-01-01"],
    ["--date-from", "2026-01-03", "--date-to", "2026-01-01"],
    CLI_ARGS + ["--fetch-limit", "0"], CLI_ARGS + ["--fetch-limit", "1001"],
    CLI_ARGS + ["--timeframes", "0m"], CLI_ARGS + ["--timeframes", "1M"],
    CLI_ARGS + ["--timezone", "Europe/Unknown"],
])
def test_cli_rejects_bad_arguments_before_network(fake_scan, args):
    with pytest.raises(SystemExit) as exc:
        scan_signals.main(args)
    assert exc.value.code == 2
    fake_scan[0].assert_not_called()
    fake_scan[1].assert_not_called()


@pytest.mark.parametrize("setting,flag,expected", [
    ("1", "--no-metric-filter", False),
    ("0", "--metric-filter", True),
])
def test_cli_metric_flag_overrides_environment(fake_scan, monkeypatch, setting, flag, expected):
    monkeypatch.setenv("SIGNAL_METRIC_FILTER_ENABLED", setting)
    scan_signals.main(CLI_ARGS)
    assert fake_scan[0].call_args.kwargs["metric_filter_enabled"] is (setting == "1")
    scan_signals.main(CLI_ARGS + [flag])
    assert fake_scan[0].call_args.kwargs["metric_filter_enabled"] is expected


def test_cli_distinguishes_empty_data_from_no_patterns(fake_scan, capsys):
    fake_scan[0].return_value = HistoricalScan(0, 0, 0, ())
    assert scan_signals.main(CLI_ARGS) == 1
    assert "No evaluable candles" in capsys.readouterr().out
    fake_scan[0].return_value = HistoricalScan(10, 6, 6, ())
    assert scan_signals.main(CLI_ARGS) == 0
    assert "Patterns found: 0" in capsys.readouterr().out


def test_cli_deduplicates_repeated_markets_and_timeframes(fake_scan):
    scan_signals.main(CLI_ARGS + ["--symbols", "btc/usdt", "BTC/USDT",
                                 "--timeframes", "15m", "15m"])
    fake_scan[0].assert_called_once()


@pytest.fixture
def test_area_store(tmp_path, monkeypatch):
    store = LevelStore(tmp_path / "levels.sqlite3")
    store.initialize()
    monkeypatch.setenv("LEVELS_DB_PATH", str(store.path))
    return store


def add_test_area(store, **changes):
    values = dict(exchange="bingx", symbol="BTC/USDT", side="buy", shape="point",
                  lower_price="90", upper_price="90", kind="level",
                  source_timeframe="1d", comment="test <b>&")
    values.update(changes)
    with store.transaction() as conn:
        return store.add(conn, **values)[0]


@pytest.mark.parametrize("changes,matched", [
    ({}, True),
    ({"lower_price": "100", "upper_price": "100"}, False),
    ({"side": "sell"}, False),
    ({"exchange": "binance"}, False),
    ({"symbol": "ETH/USDT"}, False),
    ({"shape": "zone", "kind": "imbalance", "lower_price": "80", "upper_price": "85"}, True),
])
def test_cli_checks_current_areas_without_modifying_them(
    fake_scan, test_area_store, capsys, changes, matched,
):
    area = add_test_area(test_area_store, **changes)
    with test_area_store.connection() as conn:
        before = [tuple(row) for row in conn.execute("SELECT * FROM manual_price_areas")]
    assert scan_signals.main(CLI_ARGS + ["--check-levels"]) == 0
    output = capsys.readouterr().out
    assert "Testing CURRENT active areas" in output
    assert f"Patterns matching current levels: {int(matched)}/1" in output
    if matched:
        assert f"Matched current area: #{area.id}" in output
    else:
        assert "Current levels: no match" in output
    with test_area_store.connection() as conn:
        after = [tuple(row) for row in conn.execute("SELECT * FROM manual_price_areas")]
        assert conn.execute("SELECT count(*) FROM processed_updates").fetchone()[0] == 0
    assert before == after


def test_cli_area_snapshot_is_taken_before_market_scan(fake_scan, test_area_store, capsys):
    add_test_area(test_area_store)
    result = fake_scan[0].return_value

    def scan(*args, **kwargs):
        with test_area_store.transaction() as conn:
            test_area_store.delete(conn, exchange="bingx", symbol="BTC/USDT", shape="point",
                                   lower_price="90", upper_price="90")
        return result

    fake_scan[0].side_effect = scan
    scan_signals.main(CLI_ARGS + ["--check-levels"])
    assert "Patterns matching current levels: 1/1" in capsys.readouterr().out


@pytest.mark.parametrize("db_state", ["unset", "missing", "wrong_schema"])
def test_cli_level_test_rejects_unavailable_database_before_network(
    fake_scan, monkeypatch, tmp_path, db_state,
):
    path = tmp_path / "missing.sqlite3"
    if db_state == "unset":
        monkeypatch.delenv("LEVELS_DB_PATH", raising=False)
    else:
        monkeypatch.setenv("LEVELS_DB_PATH", str(path))
    if db_state == "wrong_schema":
        store = LevelStore(path)
        store.initialize()
        with store.connection() as conn:
            conn.execute("PRAGMA user_version=999")
    with pytest.raises(SystemExit) as exc:
        scan_signals.main(CLI_ARGS + ["--check-levels"])
    assert exc.value.code == 2
    fake_scan[0].assert_not_called()
    fake_scan[1].assert_not_called()
    if db_state != "wrong_schema":
        assert not path.exists()


def test_cli_telegram_level_test_includes_escaped_annotations(
    fake_scan, test_area_store, monkeypatch,
):
    add_test_area(test_area_store)
    client = Mock()
    monkeypatch.setattr(scan_signals.TelegramConfig, "from_env", Mock(return_value=object()))
    monkeypatch.setattr(scan_signals, "TelegramClient", Mock(return_value=client))
    assert scan_signals.main(CLI_ARGS + ["--check-levels", "--send-telegram"]) == 0
    message = client.send_text.call_args.args[0]
    assert message.startswith("<b>Historical scan — current levels test</b>")
    assert "Matched current area: #" in message
    assert "source: 1d" in message and "test &lt;b&gt;&amp;" in message


def test_cli_timezone_override_reaches_scanner(fake_scan):
    scan_signals.main(CLI_ARGS + ["--timezone", "UTC"])
    assert fake_scan[0].call_args.args[3].start_ms == BASE
    scan_signals.main(CLI_ARGS)
    assert fake_scan[0].call_args.args[3].start_ms == BASE - 60 * 60 * 1000
