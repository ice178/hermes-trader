from hermes_trading.backtest.saved_signals import (
    SavedSignalRecord,
    build_signal_events_from_saved_records,
    load_saved_signal_records,
    merge_saved_signal_records,
    save_saved_signal_records,
)
from hermes_trading.candles import Candle
from hermes_trading.signal_filters import FilteredSignal
from hermes_trading.signals import SignalMatch


def _filtered_signal(
    *,
    timestamp: int = 1,
    symbol: str = "BTC/USDT",
    timeframe: str = "15m",
    pattern: str = "pin_bar",
    direction: str = "long",
) -> FilteredSignal:
    candle = Candle(
        timestamp=timestamp,
        datetime=f"2025-01-01T00:00:0{timestamp}+00:00",
        open=100.0,
        high=110.0,
        low=95.0,
        close=108.0,
        volume=250.0,
        symbol=symbol,
        timeframe=timeframe,
    )
    return FilteredSignal(
        match=SignalMatch(
            pattern=pattern,
            direction=direction,
            candle=candle,
            level=None,
        ),
        volatility_increase_pct=(25.0, 40.0),
        volume_increase_pct=(10.0, 15.0),
    )


def test_saved_signal_record_round_trip_to_signal_event() -> None:
    record = SavedSignalRecord.from_filtered_signal(_filtered_signal())
    restored = SavedSignalRecord.from_dict(record.to_dict())
    event = restored.to_signal_event()

    assert restored == record
    assert event.symbol == "BTC/USDT"
    assert event.timeframe == "15m"
    assert event.pattern == "pin_bar"
    assert event.direction == "long"
    assert event.signal_candle.timestamp == 1
    assert event.signal_candle.open == 100.0
    assert event.volatility_increase_pct == (25.0, 40.0)
    assert event.volume_increase_pct == (10.0, 15.0)


def test_merge_saved_signal_records_dedupes_by_key() -> None:
    first = SavedSignalRecord.from_filtered_signal(_filtered_signal())
    duplicate = SavedSignalRecord.from_filtered_signal(_filtered_signal())
    second = SavedSignalRecord.from_filtered_signal(_filtered_signal(timestamp=2))

    merged = merge_saved_signal_records([first], [duplicate, second])

    assert merged == [first, second]


def test_build_signal_events_from_saved_records_filters_and_dedupes() -> None:
    records = [
        SavedSignalRecord.from_filtered_signal(_filtered_signal()),
        SavedSignalRecord.from_filtered_signal(_filtered_signal()),
        SavedSignalRecord.from_filtered_signal(
            _filtered_signal(pattern="railway_tracks", timestamp=2),
        ),
        SavedSignalRecord.from_filtered_signal(
            _filtered_signal(direction="short", timestamp=3),
        ),
    ]

    events = build_signal_events_from_saved_records(
        records,
        patterns=("pin_bar",),
        directions=("long",),
        symbols=("BTC/USDT",),
        timeframes=("15m",),
    )

    assert len(events) == 1
    assert events[0].pattern == "pin_bar"
    assert events[0].direction == "long"
    assert events[0].signal_candle.timestamp == 1


def test_save_and_load_saved_signal_records_round_trip(tmp_path) -> None:
    path = tmp_path / "signals.json"
    records = [
        SavedSignalRecord.from_filtered_signal(_filtered_signal(timestamp=2)),
        SavedSignalRecord.from_filtered_signal(_filtered_signal(timestamp=1)),
    ]

    save_saved_signal_records(path, records)
    loaded = load_saved_signal_records(path)

    assert loaded == [
        SavedSignalRecord.from_filtered_signal(_filtered_signal(timestamp=1)),
        SavedSignalRecord.from_filtered_signal(_filtered_signal(timestamp=2)),
    ]
