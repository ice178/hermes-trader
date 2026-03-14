


def main() -> None:
    candle = {
        "datetime": "2025-09-16T13:00:00+00:00",
        "open": 115393.2,
        "high": 115511.0,
        "low": 114600.0,
        "close": 115154.6
    }

    open_ = candle["open"]
    close = candle["close"]
    high = candle["high"]
    low = candle["low"]

    # if open_ > close:
    #     print("Open price great than close")
    #     return

    body = abs(close - open_)
    rng = high - low
    tail = min(open_, close) - low
    head = high - max(open_, close)

    if body > rng * 0.3:
        print("Body too big")
        return

    if tail < body * 2:
        print("Tail too small")
        return

    print("This is pattern!")


if __name__ == "__main__":
    main()
