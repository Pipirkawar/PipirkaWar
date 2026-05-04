"""Тесты на доменные ошибки `domain/clan/errors.py`."""

from __future__ import annotations

from pipirik_wars.domain.clan.errors import (
    ClanAlreadyRegisteredError,
    ClanFrozenError,
    ClanMembershipExistsError,
)
from pipirik_wars.shared.errors import ConcurrencyError, DomainError


class TestClanAlreadyRegisteredError:
    def test_inherits_concurrency(self) -> None:
        err = ClanAlreadyRegisteredError(chat_id=-100123)
        assert isinstance(err, ConcurrencyError)

    def test_carries_chat_id(self) -> None:
        err = ClanAlreadyRegisteredError(chat_id=-100123)
        assert err.chat_id == -100123
        assert "-100123" in str(err)


class TestClanFrozenError:
    def test_inherits_domain(self) -> None:
        err = ClanFrozenError(chat_id=-100123)
        assert isinstance(err, DomainError)


class TestClanMembershipExistsError:
    def test_inherits_concurrency(self) -> None:
        err = ClanMembershipExistsError(clan_id=10, player_id=20)
        assert isinstance(err, ConcurrencyError)

    def test_carries_ids(self) -> None:
        err = ClanMembershipExistsError(clan_id=10, player_id=20)
        assert err.clan_id == 10
        assert err.player_id == 20
        assert "10" in str(err)
        assert "20" in str(err)
