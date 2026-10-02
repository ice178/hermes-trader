"""Foreground Telegram command daemon; supervised by systemd in production."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import logging
import os
from pathlib import Path
import signal
import sqlite3
from threading import Event
from typing import Iterator

from .level_store import LevelStore
from .telegram import TelegramClient, TelegramConfig, TelegramError
from .telegram_commands import CommandHandler

LOGGER = logging.getLogger(__name__)
POLL_TIMEOUT = 30
MAX_BACKOFF = 60
CONFIG_EXIT_CODE = 78
FATAL_API_CODES = {401, 404, 409}


@dataclass(frozen=True)
class ListenerConfig:
    db_path: Path
    allowed_user_ids: frozenset[int]

    @classmethod
    def from_env(cls) -> ListenerConfig:
        raw = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
        values = raw.split(",")
        print(values)
        if not all(value.strip().isascii() and value.strip().isdecimal()
                   and int(value) > 0 for value in values):
            raise ValueError("TELEGRAM_ALLOWED_USER_IDS requires comma-separated positive IDs")
        path = os.getenv("LEVELS_DB_PATH", "").strip()
        if not path:
            raise ValueError("LEVELS_DB_PATH is required for the command listener")
        return cls(Path(path).expanduser().resolve(), frozenset(int(value) for value in values))


@contextmanager
def listener_lock(db_path: Path) -> Iterator[None]:
    """Prevent two local listeners from using the same database."""
    lock_path = db_path.with_name(db_path.name + ".lock")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another listener owns this database lock") from None
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class LevelsListener:
    def __init__(
        self, client: TelegramClient, store: LevelStore,
        handler: CommandHandler, stop: Event,
    ) -> None:
        self.client = client
        self.store = store
        self.handler = handler
        self.stop = stop

    def drain_replies(self) -> None:
        while not self.stop.is_set():
            reply = self.store.claim_reply()
            if reply is None:
                return
            reply_id, chat_id, text = reply
            try:
                # Plain text: user comments cannot inject Telegram HTML.
                self.client.send_text(text, chat_id=chat_id)
            except TelegramError as exc:
                if exc.code == 429:
                    self.store.finish_reply(reply_id, "pending")
                    self.stop.wait(max(1, exc.retry_after))
                    return
                self.store.finish_reply(reply_id, "failed")
                LOGGER.error("Reply %s delivery failed; inspect state with /levels (code=%s)",
                             reply_id, exc.code)
                if exc.code in FATAL_API_CODES:
                    raise
            else:
                self.store.finish_reply(reply_id, "sent")

    def run(self) -> None:
        backoff = 1
        uncertain = self.store.uncertain_reply_count()
        if uncertain:
            LOGGER.warning("%s replies have uncertain delivery; they will not be resent", uncertain)
        LOGGER.info("Levels listener started")
        while not self.stop.is_set():
            try:
                self.drain_replies()
                if self.stop.is_set():
                    break
                updates = self.client.get_updates(self.store.offset(), timeout=POLL_TIMEOUT)
                for update in sorted(updates, key=lambda item: item["update_id"]):
                    if self.stop.is_set():
                        break
                    self.store.process_update(update, self.handler.handle)
                self.drain_replies()
                backoff = 1
            except TelegramError as exc:
                if exc.code in FATAL_API_CODES:
                    raise
                LOGGER.warning("Polling failed (code=%s); retrying", exc.code)
                self.stop.wait(max(backoff, exc.retry_after))
                backoff = min(MAX_BACKOFF, backoff * 2)
            except sqlite3.Error:
                LOGGER.error("Levels database unavailable; update was not acknowledged")
                self.stop.wait(backoff)
                backoff = min(MAX_BACKOFF, backoff * 2)
        LOGGER.info("Levels listener stopped")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    os.umask(0o077)
    stop = Event()
    previous = {}
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.signal(signum, lambda *_: stop.set())
    try:
        config = ListenerConfig.from_env()
        client = TelegramClient(TelegramConfig.from_env())
        config.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with listener_lock(config.db_path):
            store = LevelStore(config.db_path)
            store.initialize()
            backoff = 1
            while not stop.is_set():
                try:
                    identity = client.get_me()
                    break
                except TelegramError as exc:
                    if exc.code in FATAL_API_CODES:
                        raise
                    LOGGER.warning("Telegram identity unavailable (code=%s); retrying", exc.code)
                    stop.wait(max(backoff, exc.retry_after))
                    backoff = min(MAX_BACKOFF, backoff * 2)
            else:
                return 0
            store.bind_bot(identity["id"])
            handler = CommandHandler(config.allowed_user_ids, identity["username"])
            LevelsListener(client, store, handler, stop).run()
        return 0
    except ValueError as exc:
        LOGGER.error("Listener configuration: %s", exc)
        return CONFIG_EXIT_CODE
    except TelegramError as exc:
        LOGGER.error("Telegram refused polling (code=%s); check token, webhook, and other pollers",
                     exc.code)
        return CONFIG_EXIT_CODE
    except (OSError, sqlite3.Error):
        LOGGER.error("Listener startup/runtime failed; check database path, permissions and disk")
        return 1
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
