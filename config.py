"""Environment parsing and validation.

This module has **no import-time side effects**: it only defines the frozen
``Config`` dataclass and the ``load_config`` factory. All validation happens
when ``load_config`` is called, so importing this module never crashes and
never touches the environment, network, or filesystem.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DEFAULT_POLL_QUESTION = "What's your favorite programming language?"
DEFAULT_POLL_OPTIONS = "Python, TypeScript, Rust, Go"
DEFAULT_TIMEZONE = "Asia/Singapore"
DEFAULT_DATE_FORMAT = "%Y-%m-%d"
DEFAULT_POLL_DAY = 2  # Tuesday (0=Sun..6=Sat)
DEFAULT_VOTE_STORE_FILE = "vote_store.json"
DEFAULT_PORT = 10000  # Render's default PORT

WEEKDAY_NAMES = (
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
)


class ConfigError(ValueError):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    bot_token: str
    chat_id: int
    poll_question: str
    poll_options: tuple[str, ...]
    timezone: ZoneInfo
    date_format: str
    template_message: str | None
    template_parse_mode: str | None
    owner_ids: frozenset[int]
    poll_day: int
    vote_store_file: Path
    port: int


def _require(env: Mapping[str, str], key: str) -> str:
    value = (env.get(key) or "").strip()
    if not value:
        raise ConfigError(
            f"{key} is required. Set it in .env or environment variables."
        )
    return value


def _parse_int(raw: str, *, label: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ConfigError(f"{label} must be an integer, got {raw!r}.")


def _parse_port(raw: str) -> int:
    """Defensively parse $PORT, falling back to the default on bad input."""
    try:
        port = int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid PORT %r; falling back to %d.", raw, DEFAULT_PORT)
        return DEFAULT_PORT
    if not 0 <= port <= 65535:
        logger.warning("PORT %d out of range; falling back to %d.", port, DEFAULT_PORT)
        return DEFAULT_PORT
    return port


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Parse and validate configuration from *env* (defaults to os.environ).

    Raises ``ConfigError`` with an actionable message when a value is missing
    or invalid. Accepts an explicit mapping for testability.
    """
    env = os.environ if env is None else env

    bot_token = _require(env, "BOT_TOKEN")

    chat_id = _parse_int(_require(env, "CHAT_ID"), label="CHAT_ID")

    poll_question = env.get("POLL_QUESTION") or DEFAULT_POLL_QUESTION

    options_raw = env.get("POLL_OPTIONS") or DEFAULT_POLL_OPTIONS
    poll_options = tuple(opt.strip() for opt in options_raw.split(",") if opt.strip())
    if len(poll_options) < 2:
        raise ConfigError("At least 2 poll options are required (POLL_OPTIONS).")
    if len(poll_options) > 10:
        raise ConfigError("At most 10 poll options are allowed (POLL_OPTIONS).")
    for option in poll_options:
        if not option:
            raise ConfigError("Poll options must be non-empty (POLL_OPTIONS).")
        if len(option) > 100:
            raise ConfigError(
                f"Poll option too long (max 100 chars): {option!r} (POLL_OPTIONS)."
            )

    timezone_name = (env.get("POLL_TIMEZONE") or DEFAULT_TIMEZONE).strip()
    try:
        timezone = ZoneInfo(timezone_name)
    except Exception:
        raise ConfigError(
            f"Invalid timezone {timezone_name!r}. Use IANA names like "
            f"'UTC', 'Asia/Shanghai', 'America/New_York'."
        )

    date_format = env.get("POLL_DATE_FORMAT") or DEFAULT_DATE_FORMAT

    template_raw = env.get("TEMPLATE_MESSAGE") or ""
    # Convert literal \n to real newlines (needed for Render.com env vars).
    template_message = template_raw.replace("\\n", "\n") if template_raw else None
    template_parse_mode = (env.get("TEMPLATE_PARSE_MODE") or "").strip() or None

    owner_ids: set[int] = set()
    owners_raw = (env.get("BOT_OWNER_IDS") or "").strip()
    if owners_raw:
        for token in owners_raw.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                owner_ids.add(int(token))
            except ValueError:
                raise ConfigError(
                    f"BOT_OWNER_IDS must be comma-separated integers, got {token!r}."
                )

    poll_day_raw = (env.get("POLL_DAY") or str(DEFAULT_POLL_DAY)).strip()
    poll_day = _parse_int(poll_day_raw, label="POLL_DAY")
    if not 0 <= poll_day <= 6:
        raise ConfigError(
            f"POLL_DAY must be between 0 (Sunday) and 6 (Saturday), got {poll_day}."
        )

    vote_store_file = Path(env.get("VOTE_STORE_FILE") or DEFAULT_VOTE_STORE_FILE)

    port = _parse_port(env.get("PORT") or str(DEFAULT_PORT))

    return Config(
        bot_token=bot_token,
        chat_id=chat_id,
        poll_question=poll_question,
        poll_options=poll_options,
        timezone=timezone,
        date_format=date_format,
        template_message=template_message,
        template_parse_mode=template_parse_mode,
        owner_ids=frozenset(owner_ids),
        poll_day=poll_day,
        vote_store_file=vote_store_file,
        port=port,
    )
