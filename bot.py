"""
Telegram Auto-Poll Bot

Sends a scheduled poll to a specified Telegram chat/channel on a chosen day of the week.

Configuration via environment variables (see .env.example):
  BOT_TOKEN          — Telegram bot token from @BotFather
  CHAT_ID            — Target chat/channel ID (e.g., -1001234567890)
  POLL_QUESTION      — The poll question (max 300 chars)
  POLL_OPTIONS       — Comma-separated list of options (2-10, each max 100 chars)
  POLL_DAY           — Day of week to send (0=Sunday, 1=Monday, ..., 6=Saturday)
  POLL_TIME          — Time to send in HH:MM 24h format (default: 09:00)
  POLL_TIMEZONE      — IANA timezone (default: UTC, e.g., Asia/Shanghai, America/New_York)
  POLL_IS_ANONYMOUS  — true/false (default: true)
  POLL_MULTIPLE      — Allow multiple answers? true/false (default: false)
  POLL_OPEN_PERIOD   — Seconds the poll stays open (5-600, default: 300)
  POLL_DATE_FORMAT   — strftime format for {date} in question (default: %Y-%m-%d)

Use {date} in POLL_QUESTION to insert the current date, e.g.:
  POLL_QUESTION=What are you doing on {date}?
"""

import logging
import os
from datetime import time, datetime, timedelta

from dotenv import load_dotenv
from telegram import Update, Poll
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

POLL_DAY = int(os.getenv("POLL_DAY", "1"))  # default: Monday
POLL_TIME_STR = os.getenv("POLL_TIME", "09:00")
POLL_TIMEZONE_STR = os.getenv("POLL_TIMEZONE", "UTC")

POLL_IS_ANONYMOUS = os.getenv("POLL_IS_ANONYMOUS", "true").lower() == "true"
POLL_ALLOWS_MULTIPLE = os.getenv("POLL_ALLOWS_MULTIPLE", "false").lower() == "true"
POLL_OPEN_PERIOD = int(os.getenv("POLL_OPEN_PERIOD", "300"))
POLL_DATE_FORMAT = os.getenv("POLL_DATE_FORMAT", "%Y-%m-%d")

# --- Validation ---
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required. Set it in .env or environment variables.")
if not CHAT_ID:
    raise ValueError("CHAT_ID is required. Set it in .env or environment variables.")
if len(POLL_OPTIONS) < 2:
    raise ValueError("At least 2 poll options are required.")
if len(POLL_OPTIONS) > 10:
    raise ValueError("At most 10 poll options are allowed.")
if POLL_DAY < 0 or POLL_DAY > 6:
    raise ValueError("POLL_DAY must be 0 (Sunday) through 6 (Saturday).")
if POLL_OPEN_PERIOD < 5 or POLL_OPEN_PERIOD > 600:
    raise ValueError("POLL_OPEN_PERIOD must be between 5 and 600 seconds.")

# Parse time
try:
    hour, minute = map(int, POLL_TIME_STR.split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError
except ValueError:
    raise ValueError("POLL_TIME must be in HH:MM 24h format (e.g., 09:00, 14:30).")

# Parse timezone
try:
    import zoneinfo
    POLL_TZ = zoneinfo.ZoneInfo(POLL_TIMEZONE_STR)
except Exception:
    raise ValueError(
        f"Invalid timezone '{POLL_TIMEZONE_STR}'. Use IANA names like "
        f"'UTC', 'Asia/Shanghai', 'America/New_York'."
    )

# Day name mapping for logging
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


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


async def send_poll_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the scheduled poll to the target chat."""
    question = _format_question()
    try:
        message = await context.bot.send_poll(
            chat_id=int(CHAT_ID),
            question=question,
            options=POLL_OPTIONS,
            is_anonymous=POLL_IS_ANONYMOUS,
            allows_multiple_answers=POLL_ALLOWS_MULTIPLE,
            open_period=POLL_OPEN_PERIOD,
        )
        logger.info(
            "Poll sent successfully! Chat: %s, Question: %s, Options: %s",
            CHAT_ID, question, POLL_OPTIONS,
        )
    except Exception as e:
        logger.error("Failed to send poll: %s", e)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with bot status when /start is issued."""
    day_name = DAY_NAMES[POLL_DAY]
    example_question = _format_question()
    await update.message.reply_text(
        f"🤖 Auto-Poll Bot is running!\n\n"
        f"📅 Sends every <b>{day_name}</b> at {POLL_TIME_STR} ({POLL_TIMEZONE_STR})\n"
        f"❓ <b>{example_question}</b>\n"
        f"📋 Options: {', '.join(POLL_OPTIONS)}\n\n"
        f"Use /poll to send a test poll right now.",
        parse_mode="HTML",
    )


async def send_test_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a test poll immediately (triggered by /poll command)."""
    question = _format_question()
    try:
        message = await context.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=question,
            options=POLL_OPTIONS,
            is_anonymous=POLL_IS_ANONYMOUS,
            allows_multiple_answers=POLL_ALLOWS_MULTIPLE,
            open_period=POLL_OPEN_PERIOD,
        )
        await update.message.reply_text("✅ Test poll sent!")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send poll: {e}")
        logger.error("Test poll failed: %s", e)


def main() -> None:
    """Set up the Application, schedule the job, and start polling."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("poll", send_test_poll))

    # Schedule the weekly poll
    poll_time = time(hour=hour, minute=minute, tzinfo=POLL_TZ)
    day_name = DAY_NAMES[POLL_DAY]

    application.job_queue.run_daily(
        callback=send_poll_job,
        time=poll_time,
        days=(POLL_DAY,),
        chat_id=int(CHAT_ID),
        name="weekly_poll",
    )

    logger.info(
        "Bot started. Poll scheduled every %s at %s (%s).",
        day_name, POLL_TIME_STR, POLL_TIMEZONE_STR,
    )

    # Start polling (blocks until stopped)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()