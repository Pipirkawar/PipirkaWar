"""Тесты на доменные ошибки `domain/player/errors.py`."""

from __future__ import annotations

from pipirik_wars.domain.player.errors import (
    PlayerAlreadyRegisteredError,
    PlayerFrozenError,
)
from pipirik_wars.shared.errors import ConcurrencyError, DomainError


class TestPlayerAlreadyRegisteredError:
    def test_inherits_concurrency(self) -> None:
        err = PlayerAlreadyRegisteredError(tg_id=42)
        assert isinstance(err, ConcurrencyError)

    def test_carries_tg_id(self) -> None:
        err = PlayerAlreadyRegisteredError(tg_id=42)
        assert err.tg_id == 42
        assert "42" in str(err)


class TestPlayerFrozenError:
    def test_inherits_domain(self) -> None:
        err = PlayerFrozenError(tg_id=42)
        assert isinstance(err, DomainError)

    def test_carries_tg_id(self) -> None:
        err = PlayerFrozenError(tg_id=42)
        assert err.tg_id == 42
        assert "42" in str(err)
