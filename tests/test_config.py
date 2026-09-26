"""Tests for config.load_config — validation, defaults, and bounds."""
from __future__ import annotations

import pytest

from config import ConfigError, load_config

BASE = {"BOT_TOKEN": "123:abc", "CHAT_ID": "-1001234567890"}


def test_minimal_config_defaults():
    cfg = load_config(dict(BASE))
    assert cfg.bot_token == "123:abc"
    assert cfg.chat_id == -1001234567890
    assert cfg.poll_question == "What's your favorite programming language?"
    assert cfg.poll_options == ("Python", "TypeScript", "Rust", "Go")
    assert cfg.timezone.key == "Asia/Singapore"
    assert cfg.date_format == "%Y-%m-%d"
    assert cfg.template_message is None
    assert cfg.template_parse_mode is None
    assert cfg.owner_ids == frozenset()
    assert cfg.poll_day == 2  # Tuesday
    assert cfg.vote_store_file.name == "vote_store.json"
    assert cfg.port == 10000  # Render default


def test_missing_token_raises():
    with pytest.raises(ConfigError, match="BOT_TOKEN"):
        load_config({"CHAT_ID": "-100"})


def test_missing_chat_id_raises():
    with pytest.raises(ConfigError, match="CHAT_ID"):
        load_config({"BOT_TOKEN": "x"})


def test_non_numeric_chat_id_raises():
    with pytest.raises(ConfigError, match="CHAT_ID"):
        load_config({**BASE, "CHAT_ID": "not-a-number"})


def test_too_few_options_raises():
    with pytest.raises(ConfigError, match="At least 2"):
        load_config({**BASE, "POLL_OPTIONS": "OnlyOne"})


def test_too_many_options_raises():
    options = ", ".join(f"opt{i}" for i in range(11))
    with pytest.raises(ConfigError, match="At most 10"):
        load_config({**BASE, "POLL_OPTIONS": options})


def test_option_too_long_raises():
    long_option = "x" * 101
    with pytest.raises(ConfigError, match="too long"):
        load_config({**BASE, "POLL_OPTIONS": f"Short, {long_option}"})


def test_options_are_stripped():
    cfg = load_config({**BASE, "POLL_OPTIONS": " A , B ,C "})
    assert cfg.poll_options == ("A", "B", "C")


def test_invalid_timezone_raises():
    with pytest.raises(ConfigError, match="Invalid timezone"):
        load_config({**BASE, "POLL_TIMEZONE": "Mars/Olympus"})


def test_poll_day_out_of_range_raises():
    with pytest.raises(ConfigError, match="POLL_DAY"):
        load_config({**BASE, "POLL_DAY": "7"})
    with pytest.raises(ConfigError, match="POLL_DAY"):
        load_config({**BASE, "POLL_DAY": "-1"})


def test_poll_day_non_numeric_raises():
    with pytest.raises(ConfigError, match="POLL_DAY"):
        load_config({**BASE, "POLL_DAY": "tuesday"})


def test_poll_day_bounds_accepted():
    assert load_config({**BASE, "POLL_DAY": "0"}).poll_day == 0
    assert load_config({**BASE, "POLL_DAY": "6"}).poll_day == 6


def test_template_unescapes_newlines_and_parse_mode():
    cfg = load_config(
        {
            **BASE,
            "TEMPLATE_MESSAGE": "Line1\\nLine2",
            "TEMPLATE_PARSE_MODE": "HTML",
        }
    )
    assert cfg.template_message == "Line1\nLine2"
    assert cfg.template_parse_mode == "HTML"


def test_owner_ids_parsed():
    cfg = load_config({**BASE, "BOT_OWNER_IDS": "1, 2 ,3"})
    assert cfg.owner_ids == frozenset({1, 2, 3})


def test_owner_ids_invalid_raises():
    with pytest.raises(ConfigError, match="BOT_OWNER_IDS"):
        load_config({**BASE, "BOT_OWNER_IDS": "1,abc"})


def test_port_parsing_and_defensive_fallback():
    assert load_config({**BASE, "PORT": "8888"}).port == 8888
    assert load_config({**BASE, "PORT": "not-a-port"}).port == 10000
    assert load_config({**BASE, "PORT": "70000"}).port == 10000
