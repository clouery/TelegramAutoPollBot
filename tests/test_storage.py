"""Tests for storage.VoteStore — schema, round-trip, corruption, atomicity."""
from __future__ import annotations

import json

from storage import VoteStore


def test_seed_and_question(tmp_path):
    store = VoteStore(tmp_path / "vote_store.json")
    store.load()
    store.seed(-100, 5, "Q?")
    assert store.question(-100, 5) == "Q?"
    assert store.entries(-100, 5) == {}


def test_record_toggle(tmp_path):
    store = VoteStore(tmp_path / "vote_store.json")
    store.load()
    store.seed(-100, 5, "Q?")

    voted = store.record(
        -100, 5, 1, option="A", name="Alice", username="alice"
    )
    assert voted is True
    assert dict(store.entries(-100, 5)[1]) == {
        "option": "A",
        "name": "Alice",
        "username": "alice",
    }

    # Same option toggles off.
    voted = store.record(
        -100, 5, 1, option="A", name="Alice", username="alice"
    )
    assert voted is False
    assert store.entries(-100, 5) == {}


def test_switch_option_stays_voted(tmp_path):
    store = VoteStore(tmp_path / "vote_store.json")
    store.load()
    store.record(-100, 5, 1, option="A", name="Alice", username="")
    assert store.record(-100, 5, 1, option="B", name="Alice", username="") is True
    assert store.entries(-100, 5)[1]["option"] == "B"


def test_entries_excludes_question(tmp_path):
    store = VoteStore(tmp_path / "vote_store.json")
    store.load()
    store.seed(-100, 5, "Q?")
    store.record(-100, 5, 7, option="A", name="Bob", username="bob")
    entries = store.entries(-100, 5)
    assert list(entries.keys()) == [7]
    assert "_question" not in entries


def test_save_and_reload_round_trip(tmp_path):
    path = tmp_path / "vote_store.json"
    store = VoteStore(path)
    store.load()
    store.seed(-100, 5, "Q?")
    store.record(-100, 5, 7, option="A", name="Bob", username="bob")
    store.save()

    reloaded = VoteStore(path)
    reloaded.load()
    assert reloaded.question(-100, 5) == "Q?"
    assert reloaded.entries(-100, 5)[7]["option"] == "A"
    assert reloaded.to_dict() == store.to_dict()


def test_on_disk_schema_uses_string_keys(tmp_path):
    path = tmp_path / "vote_store.json"
    store = VoteStore(path)
    store.load()
    store.seed(-100, 5, "Q?")
    store.record(-100, 5, 7, option="A", name="Bob", username="")
    store.save()

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert list(raw.keys()) == ["-100"]
    assert list(raw["-100"].keys()) == ["5"]
    record = raw["-100"]["5"]
    assert record["_question"] == "Q?"
    assert list(record["7"].keys()) == ["option", "name", "username"]


def test_legacy_file_loads_unchanged(tmp_path):
    path = tmp_path / "vote_store.json"
    legacy = {
        "-100": {
            "5": {
                "_question": "Old Q",
                "7": {"option": "A", "name": "Bob", "username": "bob"},
            }
        }
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")

    store = VoteStore(path)
    store.load()
    assert store.question(-100, 5) == "Old Q"
    assert dict(store.entries(-100, 5)[7]) == {
        "option": "A",
        "name": "Bob",
        "username": "bob",
    }


def test_corrupt_file_is_backed_up(tmp_path):
    path = tmp_path / "vote_store.json"
    path.write_text("{ this is not json", encoding="utf-8")

    store = VoteStore(path)
    store.load()

    assert store.to_dict() == {}
    assert not path.exists()
    assert (tmp_path / "vote_store.json.corrupt").exists()


def test_missing_file_yields_empty_store(tmp_path):
    store = VoteStore(tmp_path / "does_not_exist.json")
    store.load()
    assert store.to_dict() == {}


def test_save_is_atomic_no_tmp_leftovers(tmp_path):
    path = tmp_path / "vote_store.json"
    store = VoteStore(path)
    store.load()
    store.seed(-100, 5, "Q?")
    store.save()
    store.save()

    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []
    # Existing file is complete valid JSON after replace.
    json.loads(path.read_text(encoding="utf-8"))
