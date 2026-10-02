from dataclasses import replace
from decimal import Decimal
import sqlite3

import pytest

from hermes_trading.candles import Candle, CandleBatch
from hermes_trading.level_store import LevelStore, OFFSET_MAX_AGE_SECONDS
from hermes_trading.manual_levels import matching_areas, price_text
from hermes_trading.signals import PriceActionSignal
from hermes_trading.telegram_commands import CommandHandler, parse_command, text_units


@pytest.fixture
def store(tmp_path):
    result = LevelStore(tmp_path / "levels.sqlite3")
    result.initialize()
    return result


@pytest.fixture
def handler():
    return CommandHandler(frozenset({42}), "hermes_test_bot")


def update(update_id, text, user_id=42):
    return {"update_id": update_id, "message": {
        "message_id": update_id, "from": {"id": user_id, "is_bot": False},
        "chat": {"id": -100}, "text": text,
    }}


def command(store, handler, text, update_id=1):
    store.process_update(update(update_id, text), handler.handle)
    replies = []
    while reply := store.claim_reply():
        replies.append(reply[2])
        store.finish_reply(reply[0], "sent")
    return "\n".join(replies)


def test_points_duplicates_soft_delete_and_readd_preserve_identity(store, handler):
    response = command(store, handler,
                       "/levels_add btc/usdt BINGX BUY 4H level 100 0100.00 101 | note")
    assert "Added 2; already active 1" in response
    original = store.active_areas("bingx", "BTC/USDT")
    response = command(store, handler,
                       "/levels_add BTC/USDT bingx buy 4h level 100 102 | other", 2)
    assert "Added 1; already active 1" in response
    assert store.active_areas("bingx", "BTC/USDT")[0].comment == "note"
    command(store, handler, "/levels_add BTC/USDT bingx sell 1d level 100", 3)
    response = command(store, handler, "/level_delete BTC/USDT bingx 100.0", 4)
    assert "Deleted 2" in response and "Multiple exact matches" in response
    assert "Deleted 0" in command(store, handler, "/level_delete BTC/USDT bingx 100", 5)
    command(store, handler, "/levels_add BTC/USDT bingx buy 4h level 100", 6)
    replacement = store.active_areas("bingx", "BTC/USDT")[0]
    assert replacement.id > original[-1].id
    with store.connection() as conn:
        old = conn.execute("SELECT * FROM manual_price_areas WHERE id=?", (original[0].id,)).fetchone()
        assert old["status"] == "deleted" and old["deleted_at"]


def test_timeframes_are_distinct_but_comment_does_not_bypass_duplicate(store, handler):
    for i, (timeframe, comment_text) in enumerate([("1m", "a"), ("1M", "a"), ("1M", "b")]):
        command(store, handler,
                f"/levels_add BTC/USDT bingx buy {timeframe} level 100 | {comment_text}", i)
    assert len(store.active_areas("bingx", "BTC/USDT")) == 2


def test_zones_preserve_precision_and_exact_bounds(store, handler):
    low, high = "100.000000000000000000000001", "100.000000000000000000000002"
    command(store, handler, f"/zone_add ETH/USDT bingx buy 1h imbalance {low} {high}")
    area = store.active_areas("bingx", "ETH/USDT")[0]
    assert area.lower_price == Decimal(low) and area.upper_price == Decimal(high)
    assert "Deleted 0" in command(store, handler, "/zone_delete ETH/USDT bingx 100 101", 2)
    assert "Deleted 1" in command(store, handler,
                                  f"/zone_delete ETH/USDT bingx {low} {high}", 3)


@pytest.mark.parametrize("text", [
    "/levels_add BTC/USDT bingx buy 4h level 100 nope",
    "/levels_add BTC/USDT binance buy 4h level 100",
    "/levels_add UNKNOWN/USDT bingx buy 4h level 100",
    "/levels_add BTC/USDT bingx long 4h level 100",
    "/levels_add BTC/USDT bingx buy 5h level 100",
    "/levels_add BTC/USDT bingx buy 4h imbalance 100",
    "/levels_add BTC/USDT bingx buy 4h level",
    "/zone_add BTC/USDT bingx buy 4h imbalance 100",
    "/zone_add BTC/USDT bingx buy 4h imbalance 100 101 102",
    "/zone_add BTC/USDT bingx buy 4h imbalance 100 100",
    "/zone_add BTC/USDT bingx buy 4h imbalance 101 100",
    "/zone_add BTC/USDT bingx buy 4h level 100 101",
    "/levels_add BTC/USDT bingx buy 4h level 100 | " + "x" * 501,
    "/levels BTC/USDT extra",
    "/levels XYZ/USDT",
    "/level_delete BTC/USDT bingx 100 101",
    "/zone_delete BTC/USDT bingx 100",
    "/level_delete BTC/USDT bingx 100 | comment",
    "/unknown",
])
def test_invalid_commands_reply_without_mutation(store, handler, text):
    response = command(store, handler, text)
    assert response
    assert not store.active_areas("bingx", "BTC/USDT")
    with store.connection() as conn:
        assert conn.execute("SELECT count(*) FROM manual_price_areas").fetchone()[0] == 0


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity", "1e5", "1,000", "1_000", "9" * 25])
def test_invalid_prices_rejected(price):
    with pytest.raises(ValueError):
        price_text(price)


def test_authorization_precedes_read_and_write(store, handler):
    for i, text in enumerate(["/help", "/levels", "/levels_add BTC/USDT bingx buy 4h level 100"]):
        assert store.process_update(update(i, text, user_id=999), handler.handle)
    assert not store.claim_reply()
    assert not store.active_areas("bingx", "BTC/USDT")


def test_ignores_non_messages_other_bots_and_anonymous_senders(store, handler):
    items = [
        {"update_id": 1, "edited_message": update(1, "/help")["message"]},
        update(2, "/help@other_bot"), update(3, "hello"),
        update(4, "/help"),
    ]
    items[-1]["message"]["sender_chat"] = {"id": -100}
    for item in items:
        store.process_update(item, handler.handle)
    assert not store.claim_reply()


def test_suffix_whitespace_and_freeform_comments(store, handler):
    response = command(store, handler,
                       "  /levels_add@HERMES_TEST_BOT BTC/USDT bingx buy 4h level 100 | <b>& | note  ")
    assert "<b>& | note" in response
    assert parse_command("/help@other", bot_username="hermes_test_bot") is None
    assert "Markets:" in command(store, handler, "/help", 2)


def test_list_sorts_numerically_filters_and_chunks_records(store, handler):
    for i in range(16):
        command(store, handler,
                f"/levels_add BTC/USDT bingx buy 4h level {20-i} | " + "😀" * 500, i)
    command(store, handler, "/levels_add ETH/USDT bingx buy 4h level 1", 20)
    store.process_update(update(21, "/levels BTC/USDT"), handler.handle)
    replies = []
    while reply := store.claim_reply():
        replies.append(reply[2])
    assert len(replies) > 1
    assert all(text_units(reply) <= 3500 and "Active areas: 16" in reply for reply in replies)
    assert all("ETH/USDT" not in reply for reply in replies)
    assert "5, buy" in replies[0]
    assert sum(reply.count("😀" * 500) for reply in replies) == 16


def test_update_mutation_reply_and_cursor_are_atomic(store, handler):
    item = update(123, "/levels_add BTC/USDT bingx buy 4h level 100")

    def failing_handler(conn, value):
        handler.handle(conn, value)
        raise RuntimeError("simulated crash before commit")

    with pytest.raises(RuntimeError):
        store.process_update(item, failing_handler)
    assert not store.active_areas("bingx", "BTC/USDT")
    assert store.offset() is None and store.claim_reply() is None
    assert store.process_update(item, handler.handle)
    reopened = LevelStore(store.path)
    reopened.initialize()
    assert reopened.offset() == 124
    assert not reopened.process_update(item, handler.handle)
    assert len(reopened.active_areas("bingx", "BTC/USDT")) == 1
    assert reopened.claim_reply() is not None
    assert reopened.claim_reply() is None
    assert reopened.uncertain_reply_count() == 1


def test_offset_expires_and_randomized_ids_can_be_processed(store, handler):
    command(store, handler, "/help", 1000)
    with store.transaction() as conn:
        store._set(conn, "received_at", "100")
    assert store.offset(now=100 + OFFSET_MAX_AGE_SECONDS) is None
    assert store.process_update(update(5, "/help"), handler.handle)
    assert store.offset() == 6


def test_redelivery_identity_ignores_changed_sender_metadata(store, handler):
    item = update(1, "/levels_add BTC/USDT bingx buy 4h level 100")
    assert store.process_update(item, handler.handle)
    item["message"]["from"]["username"] = "renamed_user"
    assert not store.process_update(item, handler.handle)
    assert store.claim_reply() is not None
    assert store.claim_reply() is None


def test_randomized_update_id_reuse_has_distinct_message_identity(store, handler):
    assert store.process_update(update(1, "/help"), handler.handle)
    new_message = update(1, "/levels_add BTC/USDT bingx buy 4h level 100")
    new_message["message"]["message_id"] = 99
    assert store.process_update(new_message, handler.handle)
    assert len(store.active_areas("bingx", "BTC/USDT")) == 1


def test_schema_guards_and_wal_allow_reader_during_write(store, handler):
    command(store, handler, "/levels_add BTC/USDT bingx buy 4h level 100")
    with store.transaction() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        conn.execute("UPDATE manual_price_areas SET comment='pending'")
        assert store.active_areas("bingx", "BTC/USDT")[0].comment == ""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE manual_price_areas SET lower_price='0'")
    assert store.active_areas("bingx", "BTC/USDT")[0].comment == "pending"
    store.bind_bot(1)
    with pytest.raises(ValueError, match="different"):
        store.bind_bot(2)
    with store.connection() as conn:
        conn.execute("PRAGMA user_version=999")
    with pytest.raises(ValueError, match="version"):
        store.initialize()


def test_read_does_not_create_missing_database(tmp_path):
    store = LevelStore(tmp_path / "missing.sqlite3")
    with pytest.raises(sqlite3.OperationalError):
        store.active_areas("bingx", "BTC/USDT")
    assert not store.path.exists()


def candle(index, o, h, l, c):
    return Candle(timestamp=index, datetime="2026-01-01T00:00:00Z", open=o,
                  high=h, low=l, close=c, volume=100, symbol="BTC/USDT", timeframe="15m")


@pytest.mark.parametrize("pattern,direction,bars,length", [
    ("pin_bar", "long", [(95, 97, 85, 96)], 1),
    ("pin_bar", "short", [(95, 110, 94, 96)], 1),
    ("railway_tracks", "long", [(110, 115, 98, 100), (100, 111, 99, 110)], 2),
    ("railway_tracks", "short", [(100, 115, 98, 110), (110, 111, 99, 100)], 2),
    ("inside_bar", "long", [(110, 120, 90, 100), (100.5, 111, 99, 109.5)], 2),
    ("inside_bar", "short", [(100, 120, 90, 110), (109.5, 111, 99, 100.5)], 2),
    ("buy_engulfing", "long", [(105, 120, 95, 100), (99, 110, 98, 106)], 2),
    ("sell_engulfing", "short", [(100, 120, 95, 105), (106, 110, 98, 99)], 2),
    ("buy_engulfing", "long", [(110, 130, 98, 106), (105, 106, 99, 100), (99, 112, 98, 111)], 3),
    ("sell_engulfing", "short", [(100, 130, 90, 104), (105, 110, 99, 109), (110, 112, 98, 99)], 3),
])
def test_pattern_span_matches_wicks_and_boundaries(store, handler, pattern, direction, bars, length):
    candles = [candle(i, *bar) for i, bar in enumerate(bars)]
    matches = [match for match in PriceActionSignal().evaluate_without_levels(CandleBatch(candles))
               if match.pattern == pattern and match.direction == direction
               and match.candle == candles[-1]]
    assert len(matches) == 1
    match = matches[0]
    assert match.pattern_candles == tuple(candles[-length:])
    low, high = min(c.low for c in candles), max(c.high for c in candles)
    side = "buy" if direction == "long" else "sell"
    command(store, handler, f"/levels_add BTC/USDT bingx {side} 1w level {low} {high}")
    areas = store.active_areas("bingx", "BTC/USDT")
    assert matching_areas(match, "bingx", areas) == areas
    for change in [{"status": "deleted"}, {"side": "sell" if side == "buy" else "buy"},
                   {"exchange": "binance"}, {"symbol": "ETH/USDT"}]:
        assert not matching_areas(match, "bingx", [replace(area, **change) for area in areas])


@pytest.mark.parametrize("bounds,expected", [((70, 85), True), ((97, 100), True),
                                                   ((86, 90), True), ((80, 100), True),
                                                   ((60, 84), False), ((98, 100), False)])
def test_zone_overlap_inclusive(store, handler, bounds, expected):
    bar = candle(0, 95, 97, 85, 96)
    match = PriceActionSignal().evaluate_without_levels(CandleBatch([bar]))[0]
    command(store, handler, f"/zone_add BTC/USDT bingx buy 1h imbalance {bounds[0]} {bounds[1]}")
    assert bool(matching_areas(match, "bingx", store.active_areas("bingx", "BTC/USDT"))) is expected
