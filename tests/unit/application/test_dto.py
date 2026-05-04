"""Unit-тесты pydantic-DTO на границе bot ↔ application."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipirik_wars.application.dto import (
    GrantLengthInput,
    RegisterClanInput,
    RegisterPlayerInput,
)


class TestRegisterPlayerInput:
    def test_minimal_valid(self) -> None:
        dto = RegisterPlayerInput(tg_id=12345)
        assert dto.tg_id == 12345
        assert dto.locale == "ru"
        assert dto.referrer_tg_id is None

    def test_zero_tg_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegisterPlayerInput(tg_id=0)

    def test_negative_tg_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegisterPlayerInput(tg_id=-1)

    def test_locale_pattern(self) -> None:
        RegisterPlayerInput(tg_id=1, locale="en")
        RegisterPlayerInput(tg_id=1, locale="en_US")
        with pytest.raises(ValidationError):
            RegisterPlayerInput(tg_id=1, locale="EN")
        with pytest.raises(ValidationError):
            RegisterPlayerInput(tg_id=1, locale="english")

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            RegisterPlayerInput(tg_id=1, evil="payload")  # type: ignore[call-arg]

    def test_frozen(self) -> None:
        dto = RegisterPlayerInput(tg_id=1)
        with pytest.raises(ValidationError):
            dto.tg_id = 2

    def test_username_max_length(self) -> None:
        long = "a" * 65
        with pytest.raises(ValidationError):
            RegisterPlayerInput(tg_id=1, username=long)


class TestRegisterClanInput:
    def test_valid(self) -> None:
        dto = RegisterClanInput(
            chat_id=-100123,
            chat_kind="supergroup",
            title="Клан",
            added_by_tg_id=7,
        )
        assert dto.title == "Клан"
        assert dto.chat_kind == "supergroup"

    def test_empty_title_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegisterClanInput(
                chat_id=1,
                chat_kind="group",
                title="",
                added_by_tg_id=7,
            )

    def test_invalid_chat_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegisterClanInput(
                chat_id=1,
                chat_kind="private",  # type: ignore[arg-type]
                title="Клан",
                added_by_tg_id=7,
            )


class TestGrantLengthInput:
    def test_valid(self) -> None:
        dto = GrantLengthInput(
            target_tg_id=1,
            delta_cm=10,
            reason="event reward",
            idempotency_key="grant:abcd1234",
        )
        assert dto.delta_cm == 10

    def test_short_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GrantLengthInput(
                target_tg_id=1,
                delta_cm=5,
                reason="x",
                idempotency_key="grant:abcd1234",
            )

    def test_short_idempotency_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GrantLengthInput(
                target_tg_id=1,
                delta_cm=5,
                reason="event reward",
                idempotency_key="short",
            )
