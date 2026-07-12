"""
Telegram Auto-Poll Bot

Telegram Poll Bot — send a poll on-demand via /sendpoll.

Configuration via environment variables (see .env.example):
  BOT_TOKEN          — Telegram bot token from @BotFather
  CHAT_ID            — Target chat/channel ID (e.g., -1001234567890)
  POLL_QUESTION      — The poll question (max 300 chars)
  POLL_OPTIONS       — Comma-separated list of options (2-10, each max 100 chars)
  POLL_TIMEZONE      — IANA timezone (default: Asia/Singapore)
  POLL_IS_ANONYMOUS  — true/false (default: true)
  POLL_MULTIPLE      — Allow multiple answers? true/false (default: false)
  POLL_CLOSE_DAYS    — Days until poll auto-closes (1-30, default: 7)
  POLL_DATE_FORMAT   — strftime format for {date} in question (default: %Y-%m-%d)

Use {date} in POLL_QUESTION or TEMPLATE_MESSAGE to insert the next Tuesday's date, e.g.:
  POLL_QUESTION=Training on {date}?

Set TEMPLATE_MESSAGE to send a message before the poll (with same {date}).
"""

import logging
import os
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Load .env file if present
load_dotenv()

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")

POLL_QUESTION = os.getenv("POLL_QUESTION", "What's your favorite programming language?")
POLL_OPTIONS_RAW = os.getenv("POLL_OPTIONS", "Python, TypeScript, Rust, Go")
POLL_OPTIONS = [opt.strip() for opt in POLL_OPTIONS_RAW.split(",") if opt.strip()]

POLL_TIMEZONE_STR = os.getenv("POLL_TIMEZONE", "Asia/Singapore")

POLL_IS_ANONYMOUS = os.getenv("POLL_IS_ANONYMOUS", "true").lower() == "true"
POLL_ALLOWS_MULTIPLE = os.getenv("POLL_ALLOWS_MULTIPLE", "false").lower() == "true"
POLL_CLOSE_DAYS = int(os.getenv("POLL_CLOSE_DAYS", "7"))
POLL_DATE_FORMAT = os.getenv("POLL_DATE_FORMAT", "%Y-%m-%d")

TEMPLATE_MESSAGE = os.getenv("TEMPLATE_MESSAGE", "")
if TEMPLATE_MESSAGE:
    # Convert literal \n to actual newlines (needed for Render.com env vars)
    TEMPLATE_MESSAGE = TEMPLATE_MESSAGE.replace("\\n", "\n")
TEMPLATE_PARSE_MODE = os.getenv("TEMPLATE_PARSE_MODE", "")

# --- Validation ---
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required. Set it in .env or environment variables.")
if not CHAT_ID:
    raise ValueError("CHAT_ID is required. Set it in .env or environment variables.")
if len(POLL_OPTIONS) < 2:
    raise ValueError("At least 2 poll options are required.")
if len(POLL_OPTIONS) > 10:
    raise ValueError("At most 10 poll options are allowed.")
if POLL_CLOSE_DAYS < 1 or POLL_CLOSE_DAYS > 30:
    raise ValueError("POLL_CLOSE_DAYS must be between 1 and 30 days.")


# Parse timezone
try:
    import zoneinfo
    POLL_TZ = zoneinfo.ZoneInfo(POLL_TIMEZONE_STR)
except Exception:
    raise ValueError(
        f"Invalid timezone '{POLL_TIMEZONE_STR}'. Use IANA names like "
        f"'UTC', 'Asia/Shanghai', 'America/New_York'."
    )


# --- Health-check server (keeps Render awake) ---
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format: str, *args: tuple) -> None:
        pass  # silence logs


def _start_health_server() -> None:
    port = int(os.getenv("PORT", "8000"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    logger.info("Health server listening on port %d", port)
    server.serve_forever()


def _next_weekday(from_date: datetime, target_day: int) -> datetime:
    """Return the next occurrence of target_day (0=Sun..6=Sat) on or after from_date."""
    days_ahead = target_day - from_date.weekday()
    # weekday(): 0=Mon..6=Sun. Convert: our 0=Sun -> 6, 1=Mon -> 0, ..., 6=Sat -> 5
    from_weekday = (from_date.weekday() + 1) % 7  # convert to our 0=Sun..6=Sat
    days_ahead = target_day - from_weekday
    if days_ahead <= 0:
        days_ahead += 7
    return from_date.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)


def _format_question() -> str:
    """Replace {date} placeholder with the next Tuesday's date."""
    now = datetime.now(POLL_TZ)
    target_date = _next_weekday(now, target_day=2)  # 2 = Tuesday
    date_str = target_date.strftime(POLL_DATE_FORMAT)
    return POLL_QUESTION.replace("{date}", date_str)


def _format_template() -> str | None:
    """Replace {date} in TEMPLATE_MESSAGE with the same Tuesday date, or return None."""
    if not TEMPLATE_MESSAGE:
        return None
    now = datetime.now(POLL_TZ)
    target_date = _next_weekday(now, target_day=2)  # 2 = Tuesday
    date_str = target_date.strftime(POLL_DATE_FORMAT)
    return TEMPLATE_MESSAGE.replace("{date}", date_str)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with bot status when /start is issued."""
    example_question = _format_question()
    await update.message.reply_text(
        f"🤖 Poll Bot is running!\n\n"
        f"Send /sendpoll to post this poll to the group:\n"
        f"❓ <b>{example_question}</b>\n"
        f"📋 Options: {', '.join(POLL_OPTIONS)}",
        parse_mode="HTML",
    )


async def send_test_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a template message (if configured) then a poll to the target group.

    Triggered by the /sendpoll command.
    """
    question = _format_question()
    try:
        # Send template message before the poll
        template = _format_template()
        if template:
            kwargs = {"chat_id": int(CHAT_ID), "text": template}
            if TEMPLATE_PARSE_MODE:
                kwargs["parse_mode"] = TEMPLATE_PARSE_MODE
            await context.bot.send_message(**kwargs)

        close_date = datetime.now(POLL_TZ) + timedelta(days=POLL_CLOSE_DAYS)
        message = await context.bot.send_poll(
            chat_id=int(CHAT_ID),
            question=question,
            options=POLL_OPTIONS,
            is_anonymous=POLL_IS_ANONYMOUS,
            allows_multiple_answers=POLL_ALLOWS_MULTIPLE,
            close_date=close_date,
        )
        await update.message.reply_text("✅ Poll sent to the group!")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send poll: {e}")
        logger.error("Test poll failed: %s", e)


def main() -> None:
    """Set up the Application and start polling."""
    # Start health server in background so Render keeps the bot awake
    threading.Thread(target=_start_health_server, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sendpoll", send_test_poll))

    logger.info("Bot started. Use /sendpoll to send a poll manually.")

    # Start polling (blocks until stopped)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()