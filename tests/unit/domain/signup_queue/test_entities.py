"""Unit-тесты `SignupQueueEntry` (Спринт 1.2.4)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.signup_queue import (
    SignupQueueEntry,
    SignupQueueStatus,
)


def _entry(**overrides: object) -> SignupQueueEntry:
    base: dict[str, object] = {
        "id": 1,
        "tg_id": 42,
        "username": "alice",
        "locale": "ru",
        "position": 1,
        "enqueued_at": datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return SignupQueueEntry(**base)  # type: ignore[arg-type]


class TestSignupQueueEntry:
    def test_is_frozen(self) -> None:
        entry = _entry()
        with pytest.raises(FrozenInstanceError):
            entry.tg_id = 99

    def test_uses_slots(self) -> None:
        entry = _entry()
        # `slots=True` означает отсутствие `__dict__` — сэкономленная память
        # и невозможность monkey-patch-инга случайных атрибутов.
        assert not hasattr(entry, "__dict__")
        assert hasattr(SignupQueueEntry, "__slots__")

    def test_equality_compares_all_fields(self) -> None:
        a = _entry()
        b = _entry()
        assert a == b
        assert a == _entry(tg_id=42)
        assert a != _entry(tg_id=99)
        assert a != _entry(position=2)

    def test_optional_fields_accept_none(self) -> None:
        entry = _entry(id=None, username=None, locale=None)
        assert entry.id is None
        assert entry.username is None
        assert entry.locale is None
        assert entry.tg_id == 42

    def test_position_is_one_based_in_contract(self) -> None:
        # Контракт: `position=0` валиден на момент INSERT-а (placeholder),
        # реальное значение проставляется после `enqueue`. Просто проверяем,
        # что dataclass не валидирует значение — это ответственность репозитория.
        entry = _entry(position=0)
        assert entry.position == 0


class TestSignupQueueStatus:
    def test_values(self) -> None:
        assert SignupQueueStatus.WAITING.value == "waiting"
        assert SignupQueueStatus.PROMOTED.value == "promoted"

    def test_is_str_enum(self) -> None:
        # Enum наследует от `str`, значения работают как строки.
        assert isinstance(SignupQueueStatus.WAITING, str)
        assert SignupQueueStatus.WAITING.value == "waiting"
        assert str(SignupQueueStatus.WAITING.value) == "waiting"

    def test_members(self) -> None:
        assert {member.name for member in SignupQueueStatus} == {"WAITING", "PROMOTED"}
