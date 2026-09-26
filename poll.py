"""Pure domain logic for the poll bot.

No I/O, no environment access, no globals. All time-dependent functions take
an explicit ``now`` so they are deterministic and unit-testable.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def next_weekday(from_date: date, target_day: int, *, include_today: bool = False) -> date:
    """Return the next occurrence of ``target_day``.

    ``target_day`` uses 0=Sunday..6=Saturday. By default the next occurrence is
    strictly after ``from_date``; pass ``include_today=True`` to return
    ``from_date`` itself when it already falls on ``target_day``.
    """
    if not 0 <= target_day <= 6:
        raise ValueError(f"target_day must be between 0 and 6, got {target_day}.")

    # date.weekday(): 0=Mon..6=Sun. Convert to our 0=Sun..6=Sat convention.
    current_day = (from_date.weekday() + 1) % 7
    days_ahead = (target_day - current_day) % 7
    if days_ahead == 0 and not include_today:
        days_ahead = 7
    return from_date + timedelta(days=days_ahead)


def _target_date(now: datetime, tz: ZoneInfo, poll_day: int) -> date:
    """Normalise ``now`` to ``tz`` and resolve the target date for ``poll_day``."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    return next_weekday(now, poll_day)


def format_question(
    question: str,
    now: datetime,
    tz: ZoneInfo,
    date_format: str,
    poll_day: int,
) -> str:
    """Replace ``{date}`` in *question* with the target date for ``poll_day``."""
    target = _target_date(now, tz, poll_day)
    return question.replace("{date}", target.strftime(date_format))


def format_template(
    template: str | None,
    now: datetime,
    tz: ZoneInfo,
    date_format: str,
    poll_day: int,
) -> str | None:
    """Replace ``{date}`` in *template*, or return ``None`` when unset/empty."""
    if not template:
        return None
    target = _target_date(now, tz, poll_day)
    return template.replace("{date}", target.strftime(date_format))


def build_vote_text(
    question: str,
    options: Sequence[str],
    entries: Mapping[int, Mapping[str, str]],
) -> str:
    """Build the live voting message text with per-option voter names.

    Output format is identical to the original implementation:
    a ``📊`` header, then ``opt (N👥):`` blocks with indented names (or ``—``
    when nobody voted), and a trailing ``👥 N people responded`` line.
    """
    option_voters: dict[str, list[str]] = {opt: [] for opt in options}

    for entry in entries.values():
        try:
            option = entry["option"]
            name = entry["name"]
        except (KeyError, TypeError):
            continue
        username = entry.get("username", "") if isinstance(entry, Mapping) else ""
        display = f"{name} (@{username})" if username else name
        option_voters.setdefault(option, []).append(display)

    lines = [f"📊 {question}", ""]
    for opt in options:
        voters = option_voters.get(opt, [])
        lines.append(f"{opt} ({len(voters)}👥):")
        if voters:
            lines.extend(f"  {voter}" for voter in voters)
        else:
            lines.append("  —")
        lines.append("")

    lines.append(f"👥 {len(entries)} people responded")
    return "\n".join(lines).strip()


def build_keyboard(options: Sequence[str], message_id: int) -> InlineKeyboardMarkup:
    """Build the inline keyboard with one button per option."""
    buttons = [
        [InlineKeyboardButton(option, callback_data=f"vote_{message_id}_{index}")]
        for index, option in enumerate(options)
    ]
    return InlineKeyboardMarkup(buttons)


def parse_callback_data(data: str | None) -> tuple[int, int] | None:
    """Parse ``vote_{message_id}_{option_index}`` into ``(message_id, index)``.

    Returns ``None`` for malformed or missing data.
    """
    if not data:
        return None
    parts = data.split("_")
    if len(parts) != 3 or parts[0] != "vote":
        return None
    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        return None
