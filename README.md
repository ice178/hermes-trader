# hermes-trading

Prototype trading bot framework.

## Features

- Exchange connector interface.
- Implementations for **Binance** and **BingX** using [CCXT](https://github.com/ccxt/ccxt).

## Development

Install dependencies and run tests:

```bash
pip install -e .
pytest
```

## Telegram notifications

Set credentials via environment variables and send a message:

```bash
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"
```

```python
from hermes_trading.telegram import TelegramClient, TelegramConfig

client = TelegramClient(TelegramConfig.from_env())
client.send_text("Hermes trading is online.")
```
