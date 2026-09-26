"""Vote persistence with an atomic, schema-preserving JSON store.

On-disk schema (unchanged from the original bot)::

    {
      "<chat_id>": {
        "<message_id>": {
          "_question": "...",
          "<user_id>": {"option": "...", "name": "...", "username": "..."}
        }
      }
    }

JSON object keys are always strings, so chat/message/user ids are serialised
as strings and converted back to ``int`` on load. Existing ``vote_store.json``
files load unchanged.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Mapping, Union

logger = logging.getLogger(__name__)

UserEntry = Dict[str, str]
# A message record maps either the special "_question" key to a str, or a
# user id (int at rest) to a UserEntry.
MessageRecord = Dict[Union[str, int], Union[str, UserEntry]]
VoteData = Dict[int, Dict[int, MessageRecord]]


class VoteStore:
    """Load, mutate, and atomically persist the vote store."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._data: VoteData = {}

    # -- persistence -----------------------------------------------------

    def load(self) -> None:
        """Load the store. Tolerant of legacy keys; corrupt files are backed up."""
        if not self._path.exists():
            self._data = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning(
                "Failed to parse vote store %s; backing up and starting empty.",
                self._path,
            )
            self._backup_corrupt()
            self._data = {}
            return
        self._data = self._convert(raw)

    def save(self) -> None:
        """Atomically write the store: temp file in same dir, fsync, os.replace."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(self._path.parent),
                prefix=self._path.name + ".",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(self._data, handle, default=str, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_name, self._path)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        except Exception as exc:
            logger.warning("Failed to save vote store to %s: %s", self._path, exc)

    def _backup_corrupt(self) -> None:
        corrupt_path = self._path.with_name(self._path.name + ".corrupt")
        try:
            os.replace(self._path, corrupt_path)
            logger.warning("Moved corrupt vote store to %s", corrupt_path)
        except OSError as exc:
            logger.warning("Could not back up corrupt vote store %s: %s", self._path, exc)

    @staticmethod
    def _convert_record(record: Mapping[object, object]) -> MessageRecord:
        converted: MessageRecord = {}
        for key, value in record.items():
            if key == "_question":
                converted["_question"] = value  # type: ignore[assignment]
                continue
            try:
                user_id = int(key)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                converted[key] = value  # type: ignore[index]
                continue
            if isinstance(value, dict):
                converted[user_id] = value  # type: ignore[assignment]
        return converted

    @classmethod
    def _convert(cls, raw: object) -> VoteData:
        if not isinstance(raw, dict):
            return {}
        data: VoteData = {}
        for chat_key, messages in raw.items():
            try:
                chat_id = int(chat_key)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if not isinstance(messages, dict):
                continue
            converted_messages: Dict[int, MessageRecord] = {}
            for message_key, record in messages.items():
                try:
                    message_id = int(message_key)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
                if not isinstance(record, dict):
                    continue
                converted_messages[message_id] = cls._convert_record(record)
            data[chat_id] = converted_messages
        return data

    # -- mutation --------------------------------------------------------

    def seed(self, chat_id: int, message_id: int, question: str) -> None:
        """Register a message id with its question without wiping existing votes."""
        record = self._data.setdefault(chat_id, {}).setdefault(message_id, {})
        record["_question"] = question

    def record(
        self,
        chat_id: int,
        message_id: int,
        user_id: int,
        *,
        option: str,
        name: str,
        username: str,
    ) -> bool:
        """Toggle ``user_id``'s vote. Returns True if now voted, False if removed."""
        record = self._data.setdefault(chat_id, {}).setdefault(message_id, {})
        current = record.get(user_id)
        if isinstance(current, dict) and current.get("option") == option:
            record.pop(user_id, None)
            return False
        record[user_id] = {"option": option, "name": name, "username": username}
        return True

    # -- reads -----------------------------------------------------------

    def entries(
        self, chat_id: int, message_id: int
    ) -> Mapping[int, Mapping[str, str]]:
        """Return only user entries (excludes the ``_question`` marker)."""
        record = self._data.get(chat_id, {}).get(message_id, {})
        return {
            user_id: entry
            for user_id, entry in record.items()
            if isinstance(user_id, int) and isinstance(entry, dict)
        }

    def question(self, chat_id: int, message_id: int) -> str | None:
        record = self._data.get(chat_id, {}).get(message_id, {})
        question = record.get("_question")
        return question if isinstance(question, str) else None

    def to_dict(self) -> dict:
        return copy.deepcopy(self._data)
