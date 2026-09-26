"""Tests for poll.py — pure date/format/keyboard logic."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from poll import (
    build_keyboard,
    build_vote_text,
    format_question,
    format_template,
    next_weekday,
    parse_callback_data,
)

UTC = ZoneInfo("UTC")


def test_next_weekday_strictly_after():
    monday = date(2024, 1, 1)
    assert next_weekday(monday, 2) == date(2024, 1, 2)  # Tue
    assert next_weekday(monday, 0) == date(2024, 1, 7)  # Sun
    assert next_weekday(monday, 6) == date(2024, 1, 6)  # Sat


def test_next_weekday_rolls_to_following_week():
    tuesday = date(2024, 1, 2)
    assert next_weekday(tuesday, 2) == date(2024, 1, 9)


def test_next_weekday_include_today():
    tuesday = date(2024, 1, 2)
    assert next_weekday(tuesday, 2, include_today=True) == tuesday


def test_next_weekday_invalid_target():
    with pytest.raises(ValueError):
        next_weekday(date(2024, 1, 1), 7)
    with pytest.raises(ValueError):
        next_weekday(date(2024, 1, 1), -1)


def test_format_question_next_tuesday():
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)  # Monday
    result = format_question("Training on {date}?", now, UTC, "%Y-%m-%d", 2)
    # Poll day 2 = Tuesday, so the target must be Tuesday 2024-01-02.
    assert result == "Training on 2024-01-02?"


def test_format_question_poll_day_changes_target():
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)  # Monday
    assert format_question("{date}", now, UTC, "%Y-%m-%d", 0) == "2024-01-07"  # Sun
    assert format_question("{date}", now, UTC, "%Y-%m-%d", 2) == "2024-01-02"  # Tue


def test_format_template_none_when_unset():
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    assert format_template(None, now, UTC, "%Y-%m-%d", 2) is None
    assert format_template("", now, UTC, "%Y-%m-%d", 2) is None


def test_format_template_replaces_date():
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    result = format_template("Hi {date}!", now, UTC, "%Y-%m-%d", 2)
    assert result == "Hi 2024-01-02!"


def test_build_vote_text_formatting():
    entries = {
        1: {"option": "A", "name": "Alice", "username": "alice"},
        2: {"option": "B", "name": "Bob", "username": ""},
        3: {"option": "A", "name": "Carol", "username": "carol"},
    }
    text = build_vote_text("Q", ("A", "B"), entries)
    assert text == (
        "📊 Q\n"
        "\n"
        "A (2👥):\n"
        "  Alice (@alice)\n"
        "  Carol (@carol)\n"
        "\n"
        "B (1👥):\n"
        "  Bob\n"
        "\n"
        "👥 3 people responded"
    )


def test_build_vote_text_empty_entries():
    text = build_vote_text("Q", ("A", "B"), {})
    assert text == (
        "📊 Q\n"
        "\n"
        "A (0👥):\n"
        "  —\n"
        "\n"
        "B (0👥):\n"
        "  —\n"
        "\n"
        "👥 0 people responded"
    )


def test_build_keyboard_callback_data():
    keyboard = build_keyboard(("A", "B"), 42)
    assert len(keyboard.inline_keyboard) == 2
    assert keyboard.inline_keyboard[0][0].callback_data == "vote_42_0"
    assert keyboard.inline_keyboard[1][0].callback_data == "vote_42_1"


def test_parse_callback_data_valid():
    assert parse_callback_data("vote_42_1") == (42, 1)


def test_parse_callback_data_invalid():
    assert parse_callback_data(None) is None
    assert parse_callback_data("") is None
    assert parse_callback_data("nope") is None
    assert parse_callback_data("vote_42") is None
    assert parse_callback_data("vote_x_1") is None
    assert parse_callback_data("other_42_1") is None
