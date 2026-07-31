"""Send a hardcoded test Telegram message using environment credentials."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    # Ensure src/ is on sys.path for direct script execution.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hermes_trading.telegram import TelegramClient, TelegramConfig


def main() -> int:
    client = TelegramClient(TelegramConfig.from_env())
    client.send_text("Hello")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
