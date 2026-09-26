"""Telegram handler factories.

Each ``make_*`` function closes over an injected :class:`~config.Config` and
:class:`~storage.VoteStore`, so there are no import-time globals or side
effects. Callback data keeps the historic ``vote_{message_id}_{index}`` format
for backward compatibility with already-posted messages.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Awaitable, Callable

from telegram import Update
from telegram.ext import ContextTypes

from config import Config, WEEKDAY_NAMES
from poll import (
    build_keyboard,
    build_vote_text,
    format_question,
    format_template,
    parse_callback_data,
)
from storage import VoteStore

logger = logging.getLogger(__name__)

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]


def make_start(cfg: Config) -> Handler:
    """Factory for the ``/start`` handler."""

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.now(cfg.timezone)
        example_question = format_question(
            cfg.poll_question, now, cfg.timezone, cfg.date_format, cfg.poll_day
        )
        await update.message.reply_text(
            f"🤖 Poll Bot is running!\n\n"
            f"Send /sendpoll to post this poll to the group:\n"
            f"❓ <b>{example_question}</b>\n"
            f"📋 Options: {', '.join(cfg.poll_options)}",
            parse_mode="HTML",
        )

    return start


async def _notify_owner_sendpoll(
    cfg: Config,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    user_name: str,
    user_username: str,
    chat_info: str,
    authorized: bool,
) -> None:
    """Notify each configured owner about a /sendpoll attempt (best effort)."""
    for owner_id in cfg.owner_ids:
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
        except Exception as exc:  # noqa: BLE001 - best-effort notification
            logger.warning("Failed to notify owner %s: %s", owner_id, exc)


def make_send_poll(cfg: Config, store: VoteStore) -> Handler:
    """Factory for the ``/sendpoll`` handler."""

    async def send_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        user_id = user.id if user else 0
        user_name = user.full_name if user else "Unknown"
        user_username = (user.username or "") if user else ""
        chat_type = update.effective_chat.type if update.effective_chat else "?"
        chat_title = (
            update.effective_chat.title or "DM" if update.effective_chat else "?"
        )
        chat_info = f"{chat_type} ({chat_title})"

        authorized = bool(cfg.owner_ids and user and user.id in cfg.owner_ids)
        try:
            context.application.create_task(
                _notify_owner_sendpoll(
                    cfg,
                    context,
                    user_id,
                    user_name,
                    user_username,
                    chat_info,
                    authorized,
                )
            )
        except Exception as exc:  # noqa: BLE001 - never block /sendpoll
            logger.warning("Failed to schedule owner notification: %s", exc)

        if cfg.owner_ids and (not user or user.id not in cfg.owner_ids):
            logger.warning(
                "Unauthorized /sendpoll by user=%s (id=%d, username=%s) in %s",
                user_name,
                user_id,
                user_username,
                chat_info,
            )
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return

        now = datetime.now(cfg.timezone)
        question = format_question(
            cfg.poll_question, now, cfg.timezone, cfg.date_format, cfg.poll_day
        )
        try:
            template = format_template(
                cfg.template_message, now, cfg.timezone, cfg.date_format, cfg.poll_day
            )
            if template:
                kwargs: dict = {"chat_id": cfg.chat_id, "text": template}
                if cfg.template_parse_mode:
                    kwargs["parse_mode"] = cfg.template_parse_mode
                await context.bot.send_message(**kwargs)

            initial_text = f"📊 {question}\n\nTap a button below to vote!"
            # Send first to obtain a message_id, then attach the keyboard.
            message = await context.bot.send_message(
                chat_id=cfg.chat_id,
                text=initial_text,
            )

            store.seed(cfg.chat_id, message.message_id, question)
            store.save()

            keyboard = build_keyboard(cfg.poll_options, message.message_id)
            await context.bot.edit_message_text(
                initial_text,
                chat_id=cfg.chat_id,
                message_id=message.message_id,
                reply_markup=keyboard,
            )

            await update.message.reply_text("✅ Voting message sent to the group!")
        except Exception as exc:  # noqa: BLE001 - log details, reply generically
            logger.error("Voting message failed: %s", exc, exc_info=True)
            await update.message.reply_text(
                "❌ Failed to send voting message. Please check the bot logs."
            )

    return send_poll


def make_handle_vote(cfg: Config, store: VoteStore) -> Handler:
    """Factory for the inline-button vote callback handler."""

    async def handle_vote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return

        # Answer as early as possible so the button stops spinning. A failed
        # answer (already answered / query too old) must not stop vote handling.
        try:
            await query.answer()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Callback answer failed (non-fatal): %s", exc)

        parsed = parse_callback_data(query.data)
        if parsed is None:
            logger.warning("Malformed callback data: %r", getattr(query, "data", None))
            return
        msg_id, opt_idx = parsed

        if opt_idx < 0 or opt_idx >= len(cfg.poll_options):
            return

        user = query.from_user
        if not user:
            return

        chat_id = query.message.chat_id if query.message else 0
        chosen_option = cfg.poll_options[opt_idx]
        logger.info(
            "Vote received: user=%s (id=%s) -> %s | msg=%s | chat=%s",
            user.full_name,
            user.id,
            chosen_option,
            msg_id,
            chat_id,
        )

        store.record(
            chat_id,
            msg_id,
            user.id,
            option=chosen_option,
            name=user.full_name,
            username=user.username or "",
        )
        store.save()

        question = store.question(chat_id, msg_id)
        if question is None:
            now = datetime.now(cfg.timezone)
            question = format_question(
                cfg.poll_question, now, cfg.timezone, cfg.date_format, cfg.poll_day
            )

        new_text = build_vote_text(
            question, cfg.poll_options, store.entries(chat_id, msg_id)
        )
        keyboard = build_keyboard(cfg.poll_options, msg_id)

        try:
            # Edit by explicit chat_id + message_id so we don't depend on
            # query.message being a fully-accessible Message object.
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=new_text,
                reply_markup=keyboard,
            )
        except Exception as exc:  # noqa: BLE001
            if "not modified" not in str(exc).lower():
                logger.warning("Failed to edit voting message: %s", exc)

    return handle_vote
