"""Unit-тесты ошибок `signup_queue` (Спринт 1.2.4)."""

from __future__ import annotations

from pipirik_wars.domain.signup_queue import (
    AlreadyQueuedError,
    SignupQueueError,
)
from pipirik_wars.shared.errors import DomainError


class TestSignupQueueError:
    def test_is_domain_error(self) -> None:
        error = SignupQueueError("any text")
        assert isinstance(error, DomainError)


class TestAlreadyQueuedError:
    def test_is_signup_queue_error(self) -> None:
        error = AlreadyQueuedError(tg_id=42)
        assert isinstance(error, SignupQueueError)
        assert isinstance(error, DomainError)

    def test_holds_tg_id(self) -> None:
        error = AlreadyQueuedError(tg_id=12345)
        assert error.tg_id == 12345

    def test_str_contains_tg_id(self) -> None:
        error = AlreadyQueuedError(tg_id=777)
        text = str(error)
        assert "777" in text
        assert "tg_id" in text
