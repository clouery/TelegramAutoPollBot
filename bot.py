"""
Telegram Auto-Poll Bot

Telegram Poll Bot — send a poll on-demand via /sendpoll.

Configuration via environment variables (see .env.example):
  BOT_TOKEN          — Telegram bot token from @BotFather
  CHAT_ID            — Target chat/channel ID (e.g., -1001234567890)
  POLL_QUESTION      — The poll question (max 300 chars)
  POLL_OPTIONS       — Comma-separated list of options (2-10, each max 100 chars)
  POLL_TIMEZONE      — IANA timezone (default: Asia/Singapore)
  POLL_DATE_FORMAT   — strftime format for {date} in question (default: %Y-%m-%d)
  POLL_DAY           — Day of week to auto-send (0=Sun..6=Sat)
  POLL_TIME          — Time to auto-send in HH:MM 24h
  BOT_OWNER_IDS      — Comma-separated user IDs allowed to use /sendpoll (empty = anyone)

Use {date} in POLL_QUESTION or TEMPLATE_MESSAGE to insert the next Tuesday's date, e.g.:
  POLL_QUESTION=Training on {date}?

Set TEMPLATE_MESSAGE to send a message before the poll (with same {date}).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import threading

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

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

POLL_DATE_FORMAT = os.getenv("POLL_DATE_FORMAT", "%Y-%m-%d")

TEMPLATE_MESSAGE = os.getenv("TEMPLATE_MESSAGE", "")
if TEMPLATE_MESSAGE:
    # Convert literal \n to actual newlines (needed for Render.com env vars)
    TEMPLATE_MESSAGE = TEMPLATE_MESSAGE.replace("\\n", "\n")
TEMPLATE_PARSE_MODE = os.getenv("TEMPLATE_PARSE_MODE", "")

# Optional: comma-separated Telegram user IDs allowed to use /sendpoll (leave empty to allow anyone)
BOT_OWNER_IDS_RAW = os.getenv("BOT_OWNER_IDS", "")
BOT_OWNER_IDS = {int(x.strip()) for x in BOT_OWNER_IDS_RAW.split(",") if x.strip()}

# --- Validation ---
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required. Set it in .env or environment variables.")
if not CHAT_ID:
    raise ValueError("CHAT_ID is required. Set it in .env or environment variables.")
if len(POLL_OPTIONS) < 2:
    raise ValueError("At least 2 poll options are required.")
if len(POLL_OPTIONS) > 10:
    raise ValueError("At most 10 poll options are allowed.")


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


# --- Persistence ---
VOTE_STORE_FILE = Path(os.getenv("VOTE_STORE_FILE", "vote_store.json"))


def _load_vote_store() -> dict[int, dict[int, dict]]:
    """Load vote_store from JSON file, converting string keys back to ints."""
    if not VOTE_STORE_FILE.exists():
        return {}
    try:
        raw = json.loads(VOTE_STORE_FILE.read_text())
        # Convert string-keyed chat_ids and msg_ids back to int; keep "_question" as-is
        return {
            int(chat_id): {
                int(msg_id): {
                    int(k) if k.lstrip("-").isdigit() else k: v
                    for k, v in msg.items()
                }
                for msg_id, msg in msgs.items()
            }
            for chat_id, msgs in raw.items()
        }
    except Exception:
        logger.warning("Failed to load vote store from %s, starting fresh.", VOTE_STORE_FILE)
        return {}


def _save_vote_store() -> None:
    """Write vote_store to JSON file."""
    try:
        VOTE_STORE_FILE.write_text(json.dumps(vote_store, default=str, indent=2))
    except Exception:
        logger.warning("Failed to save vote store to %s", VOTE_STORE_FILE)


# --- Inline-button voting (like CountMeInBot) ---
# {chat_id: {msg_id: {"_question": str, user_id: {"option": str, "name": str, "username": str}}}}
vote_store: dict[int, dict[int, dict]] = _load_vote_store()


def _build_vote_text(question: str, store: dict[int, dict[str, str]]) -> str:
    """Build the voting message text with per-option name lists."""
    # Count votes per option
    from_collection = [v for v in store.values() if isinstance(v, dict)]
    option_counts: dict[str, int] = {}
    option_voters: dict[str, list[str]] = {}
    for opt in POLL_OPTIONS:
        option_counts[opt] = 0
        option_voters[opt] = []

    for entry in from_collection:
        opt = entry["option"]
        name = entry["name"]
        username = entry.get("username", "")
        display = f"{name} (@{username})" if username else name
        option_counts[opt] = option_counts.get(opt, 0) + 1
        option_voters.setdefault(opt, []).append(display)

    lines = [f"📊 {question}", ""]
    for opt in POLL_OPTIONS:
        count = option_counts.get(opt, 0)
        lines.append(f"{opt} ({count}👥):")
        if option_voters.get(opt):
            lines.extend(f"  {v}" for v in option_voters[opt])
        else:
            lines.append("  —")
        lines.append("")

    lines.append(f"👥 {len(from_collection)} people responded")
    return "\n".join(lines).strip()


async def handle_vote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses — toggle user vote and update the message."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    # Parse callback data: "vote_{message_id}_{option_index}"
    try:
        _, msg_id_str, opt_idx_str = query.data.split("_")
    except (ValueError, AttributeError):
        return

    chat_id = query.message.chat_id if query.message else 0
    msg_id = int(msg_id_str)
    opt_idx = int(opt_idx_str)

    if opt_idx < 0 or opt_idx >= len(POLL_OPTIONS):
        return

    user = query.from_user
    if not user:
        return

    chosen_option = POLL_OPTIONS[opt_idx]

    # Update the store
    chat_store = vote_store.setdefault(chat_id, {})
    user_store = chat_store.setdefault(msg_id, {})

    current = user_store.get(user.id)
    if current and current["option"] == chosen_option:
        # Same button → toggle off
        user_store.pop(user.id, None)
    else:
        # Different or new vote
        user_store[user.id] = {
            "option": chosen_option,
            "name": user.full_name,
            "username": user.username or "",
        }

    _save_vote_store()

    # Rebuild and edit the message text (preserve buttons)
    question = user_store.get("_question", _format_question())
    new_text = _build_vote_text(question, user_store)

    # Rebuild keyboard (buttons stay the same)
    keyboard = _build_keyboard(msg_id)

    try:
        await query.edit_message_text(
            new_text,
            reply_markup=keyboard,
        )
    except Exception as e:
        if "not modified" not in str(e).lower():
            logger.warning("Failed to edit voting message: %s", e)


def _build_keyboard(message_id: int) -> InlineKeyboardMarkup:
    """Build the inline keyboard with one button per option."""
    buttons = [
        [InlineKeyboardButton(opt, callback_data=f"vote_{message_id}_{i}")]
        for i, opt in enumerate(POLL_OPTIONS)
    ]
    return InlineKeyboardMarkup(buttons)


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


async def _notify_owner_sendpoll(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    user_name: str,
    user_username: str,
    chat_info: str,
    authorized: bool,
) -> None:
    """Send a notification to the bot owner about a /sendpoll attempt."""
    for owner_id in BOT_OWNER_IDS:
        try:
            username_line = f"📱 Username: @{user_username}\n" if user_username else ""
            icon = "✅" if authorized else "⚠️"
            label = "Authorized" if authorized else "Unauthorized"
            text = (
                f"{icon} {label} /sendpoll\n\n"
                f"👤 ID: <code>{user_id}</code>\n"
                f"👤 Name: {user_name}\n"
                f"{username_line}"
                f"💬 Chat: {chat_info}"
            )
            await context.bot.send_message(
                chat_id=owner_id,
                text=text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Failed to notify owner %s: %s", owner_id, e)


async def send_test_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a template message (if configured) then a voting message with inline buttons.

    Users tap buttons (e.g. "Coming" / "Not Coming") to cast their vote.
    The message updates live with names of who voted.

    Triggered by the /sendpoll command (DM the bot privately).
    """
    user = update.effective_user
    user_id = user.id if user else 0
    user_name = user.full_name if user else "Unknown"
    user_username = user.username or "" if user else ""
    chat_type = update.effective_chat.type if update.effective_chat else "?"
    chat_title = update.effective_chat.title or "DM" if update.effective_chat else "?"
    chat_info = f"{chat_type} ({chat_title})"

    authorized = bool(BOT_OWNER_IDS and user and user.id in BOT_OWNER_IDS)
    asyncio.ensure_future(
        _notify_owner_sendpoll(context, user_id, user_name, user_username, chat_info, authorized)
    )

    if BOT_OWNER_IDS and (not user or user.id not in BOT_OWNER_IDS):
        logger.warning(
            "Unauthorized /sendpoll by user=%s (id=%d, username=%s) in %s",
            user_name, user_id, user_username, chat_info,
        )
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    question = _format_question()
    try:
        # Send template message before the voting message
        template = _format_template()
        if template:
            kwargs = {"chat_id": int(CHAT_ID), "text": template}
            if TEMPLATE_PARSE_MODE:
                kwargs["parse_mode"] = TEMPLATE_PARSE_MODE
            await context.bot.send_message(**kwargs)

        # Build initial text + keyboard
        initial_text = f"📊 {question}\n\nTap a button below to vote!"
        # We send first to get a message_id, then build the keyboard with it
        message = await context.bot.send_message(
            chat_id=int(CHAT_ID),
            text=initial_text,
        )

        # Register in vote store and attach keyboard
        chat_store = vote_store.setdefault(int(CHAT_ID), {})
        chat_store[message.message_id] = {"_question": question}
        _save_vote_store()

        keyboard = _build_keyboard(message.message_id)
        await context.bot.edit_message_text(
            initial_text,
            chat_id=int(CHAT_ID),
            message_id=message.message_id,
            reply_markup=keyboard,
        )

        await update.message.reply_text("✅ Voting message sent to the group!")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send voting message: {e}")
        logger.error("Voting message failed: %s", e)


def main() -> None:
    """Set up the Application and start polling."""
    # Start health server in background so Render keeps the bot awake
    threading.Thread(target=_start_health_server, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sendpoll", send_test_poll))

    # Handle inline button taps on voting messages
    application.add_handler(CallbackQueryHandler(handle_vote, pattern=r"^vote_"))

    logger.info("Bot started. Admin can use /sendpoll to post a voting message.")

    # Start polling (blocks until stopped)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()