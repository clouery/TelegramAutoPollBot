"""Telegram Auto-Poll Bot — slim entry point.

Posts inline-button voting messages **manually only**, via the ``/sendpoll``
command. There is no scheduler and no auto-send.

Configuration via environment variables (see .env.example):
  BOT_TOKEN          — Telegram bot token from @BotFather
  CHAT_ID            — Target chat/channel ID (e.g., -1001234567890)
  POLL_QUESTION      — The poll question (use {date} for the target date)
  POLL_OPTIONS       — Comma-separated list of options (2-10, each max 100 chars)
  POLL_TIMEZONE      — IANA timezone (default: Asia/Singapore)
  POLL_DATE_FORMAT   — strftime format for {date} in question (default: %Y-%m-%d)
  POLL_DAY           — Target weekday (0=Sun..6=Sat, default 2=Tuesday)
  BOT_OWNER_IDS      — Comma-separated user IDs allowed to use /sendpoll (empty = anyone)
  LOG_LEVEL          — Logging level (default: INFO)
  PORT               — Health server port (default: 10000)
  VOTE_STORE_FILE    — Path to the vote store JSON (default: vote_store.json)

Use {date} in POLL_QUESTION or TEMPLATE_MESSAGE to insert the next target
weekday's date, e.g. POLL_QUESTION=Training on {date}?

Set TEMPLATE_MESSAGE to send a message before the poll (with the same {date}).
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from config import WEEKDAY_NAMES, ConfigError, load_config
from handlers import make_handle_vote, make_send_poll, make_start
from health import serve_in_background
from storage import VoteStore

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Configure logging in main() (never at import time)."""
    level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=level,
    )
    # Keep noisy HTTP clients quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main() -> None:
    """Load config, start the health server, wire handlers, and poll."""
    load_dotenv()
    _configure_logging()

    try:
        cfg = load_config(os.environ)
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        raise SystemExit(2)

    logger.info(
        "Target weekday: %s (POLL_DAY=%d)",
        WEEKDAY_NAMES[cfg.poll_day],
        cfg.poll_day,
    )

    store = VoteStore(cfg.vote_store_file)
    store.load()

    # Binds synchronously; bind errors surface here.
    serve_in_background(cfg.port)

    app = Application.builder().token(cfg.bot_token).build()
    app.add_handler(CommandHandler("start", make_start(cfg)))
    app.add_handler(CommandHandler("sendpoll", make_send_poll(cfg, store)))
    app.add_handler(
        CallbackQueryHandler(make_handle_vote(cfg, store), pattern=r"^vote_")
    )

    logger.info("Bot started. Admin can use /sendpoll to post a voting message.")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
