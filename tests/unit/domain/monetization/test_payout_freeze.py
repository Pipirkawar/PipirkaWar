"""Тесты доменной сущности ``PayoutFreeze`` и фейка ``FakePayoutFreezeRepository``.

Спринт 4.1-E (E.4). Покрывают:

* ``PayoutFreeze`` entity — invariants ``__post_init__``:
  - ``is_frozen=True`` требует все три атрибута (``frozen_by_admin_id``,
    ``frozen_at``, ``reason``) заполненными;
  - ``is_frozen=False`` требует все три атрибута равными ``None``;
  - ``frozen_at`` обязан быть TZ-aware;
  - ``frozen_by_admin_id`` обязан быть положительным `int`;
  - ``reason`` обязан быть непустой `str`;
* фабрики ``PayoutFreeze.unfrozen()`` / ``PayoutFreeze.frozen(...)``;
* immutability frozen-entity;
* ``FakePayoutFreezeRepository`` — ``get_state`` / ``set_frozen`` /
  ``set_unfrozen`` контракт (идемпотентность, состояние, лог-вызовы).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.monetization import PayoutFreeze
from tests.fakes.payout_freeze_repo import FakePayoutFreezeRepository


class TestPayoutFreezeUnfrozenFactory:
    def test_factory_returns_clean_unfrozen_state(self) -> None:
        state = PayoutFreeze.unfrozen()
        assert state.is_frozen is False
        assert state.frozen_by_admin_id is None
        assert state.frozen_at is None
        assert state.reason is None

    def test_factory_is_idempotent(self) -> None:
        s1 = PayoutFreeze.unfrozen()
        s2 = PayoutFreeze.unfrozen()
        assert s1 == s2


class TestPayoutFreezeFrozenFactory:
    def test_factory_builds_frozen_state(self) -> None:
        at = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)
        state = PayoutFreeze.frozen(admin_id=7, at=at, reason="suspicious activity")
        assert state.is_frozen is True
        assert state.frozen_by_admin_id == 7
        assert state.frozen_at == at
        assert state.reason == "suspicious activity"

    def test_factory_requires_positive_admin_id(self) -> None:
        with pytest.raises(ValueError, match="frozen_by_admin_id"):
            PayoutFreeze.frozen(
                admin_id=0,
                at=datetime(2026, 5, 12, tzinfo=UTC),
                reason="r",
            )

    def test_factory_requires_tz_aware_datetime(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            PayoutFreeze.frozen(
                admin_id=1,
                at=datetime(2026, 5, 12, 12, 0),  # naïve
                reason="r",
            )

    def test_factory_requires_non_empty_reason(self) -> None:
        with pytest.raises(ValueError, match="non-empty reason"):
            PayoutFreeze.frozen(
                admin_id=1,
                at=datetime(2026, 5, 12, tzinfo=UTC),
                reason="   ",
            )


class TestPayoutFreezeInvariants:
    def test_frozen_state_requires_admin_id(self) -> None:
        with pytest.raises(ValueError, match="requires frozen_by_admin_id"):
            PayoutFreeze(
                is_frozen=True,
                frozen_by_admin_id=None,
                frozen_at=datetime(2026, 5, 12, tzinfo=UTC),
                reason="r",
            )

    def test_frozen_state_requires_frozen_at(self) -> None:
        with pytest.raises(ValueError, match="requires frozen_at"):
            PayoutFreeze(
                is_frozen=True,
                frozen_by_admin_id=1,
                frozen_at=None,
                reason="r",
            )

    def test_frozen_state_requires_reason(self) -> None:
        with pytest.raises(ValueError, match="non-empty reason"):
            PayoutFreeze(
                is_frozen=True,
                frozen_by_admin_id=1,
                frozen_at=datetime(2026, 5, 12, tzinfo=UTC),
                reason=None,
            )

    def test_unfrozen_state_must_be_clean(self) -> None:
        with pytest.raises(ValueError, match="must have frozen_by_admin_id"):
            PayoutFreeze(
                is_frozen=False,
                frozen_by_admin_id=7,  # «осиротевший» frozen_by_admin_id
                frozen_at=None,
                reason=None,
            )

    def test_is_frozen_must_be_bool(self) -> None:
        with pytest.raises(TypeError, match="must be bool"):
            PayoutFreeze(
                is_frozen=1,  # type: ignore[arg-type]
                frozen_by_admin_id=None,
                frozen_at=None,
                reason=None,
            )

    def test_immutable(self) -> None:
        state = PayoutFreeze.unfrozen()
        with pytest.raises(dataclasses.FrozenInstanceError):
            state.is_frozen = True


class TestFakePayoutFreezeRepository:
    @pytest.mark.asyncio
    async def test_default_state_is_unfrozen(self) -> None:
        repo = FakePayoutFreezeRepository()
        state = await repo.get_state()
        assert state == PayoutFreeze.unfrozen()
        assert repo.get_state_calls == 1

    @pytest.mark.asyncio
    async def test_set_frozen_transitions_state(self) -> None:
        repo = FakePayoutFreezeRepository()
        at = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)
        new_state = await repo.set_frozen(admin_id=7, at=at, reason="abuse")
        assert new_state.is_frozen is True
        assert new_state.frozen_by_admin_id == 7
        assert new_state.frozen_at == at
        assert new_state.reason == "abuse"
        # Лог вызова сохранён
        assert len(repo.set_frozen_calls) == 1
        call = repo.set_frozen_calls[0]
        assert (call.admin_id, call.at, call.reason) == (7, at, "abuse")
        # Повторный get_state видит новое состояние
        assert await repo.get_state() == new_state

    @pytest.mark.asyncio
    async def test_set_unfrozen_transitions_back_to_clean_state(self) -> None:
        repo = FakePayoutFreezeRepository()
        await repo.set_frozen(
            admin_id=7,
            at=datetime(2026, 5, 12, tzinfo=UTC),
            reason="r",
        )
        new_state = await repo.set_unfrozen()
        assert new_state == PayoutFreeze.unfrozen()
        assert repo.set_unfrozen_calls == 1

    @pytest.mark.asyncio
    async def test_set_unfrozen_idempotent_on_clean_state(self) -> None:
        repo = FakePayoutFreezeRepository()
        s1 = await repo.set_unfrozen()
        s2 = await repo.set_unfrozen()
        assert s1 == s2 == PayoutFreeze.unfrozen()
        assert repo.set_unfrozen_calls == 2

    @pytest.mark.asyncio
    async def test_set_frozen_idempotent_with_same_admin(self) -> None:
        """Повторный freeze того же админа обновит reason/at, но state останется frozen."""
        repo = FakePayoutFreezeRepository()
        at1 = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)
        at2 = datetime(2026, 5, 12, 13, 0, tzinfo=UTC)
        s1 = await repo.set_frozen(admin_id=7, at=at1, reason="r1")
        s2 = await repo.set_frozen(admin_id=7, at=at2, reason="r2")
        assert s1.is_frozen is True
        assert s2.is_frozen is True
        assert s2.frozen_at == at2
        assert s2.reason == "r2"
        assert len(repo.set_frozen_calls) == 2
