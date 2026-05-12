"""In-memory реализация ``IPayoutFreezeRepository`` для unit-тестов (Спринт 4.1-E).

Имитирует ``SqlAlchemyPayoutFreezeRepository`` (E.11):

* ``get_state()`` — возвращает текущий снапшот; на свежем fake-репозитории
  даёт ``PayoutFreeze.unfrozen()``.
* ``set_frozen(*, admin_id, at, reason)`` — переключает состояние в
  ``is_frozen=True``. Идемпотентен: повторный вызов того же админа
  обновит ``reason``/``at``, но `state` остаётся `is_frozen=True`.
* ``set_unfrozen()`` — переключает состояние в ``is_frozen=False`` со
  сбросом всех nullable-атрибутов. Идемпотентен: повторный вызов на
  уже-unfrozen-состоянии — no-op.

Использование:

    repo = FakePayoutFreezeRepository()
    state = await repo.get_state()
    assert state.is_frozen is False

    new_state = await repo.set_frozen(
        admin_id=7,
        at=datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        reason="suspicious activity",
    )
    assert new_state.is_frozen is True
    assert new_state.frozen_by_admin_id == 7

Тесты use-case-ов ``FreezePayouts`` / ``UnfreezePayouts`` / ``ClaimPrize``
читают ``repo.state`` / ``repo.calls`` напрямую для assert-ов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pipirik_wars.domain.monetization.entities import PayoutFreeze
from pipirik_wars.domain.monetization.ports import IPayoutFreezeRepository


@dataclass(frozen=True, slots=True)
class FakePayoutFreezeSetFrozenCall:
    """Запись о вызове ``set_frozen(...)`` (для assert-ов в тестах)."""

    admin_id: int
    at: datetime
    reason: str


@dataclass
class FakePayoutFreezeRepository(IPayoutFreezeRepository):
    """In-memory реализация для тестов use-case-ов.

    Поля:

    * ``state`` — текущий снапшот ``PayoutFreeze``. Дефолт
      ``PayoutFreeze.unfrozen()``.
    * ``set_frozen_calls`` — append-only лог вызовов ``set_frozen(...)``.
    * ``set_unfrozen_calls`` — счётчик вызовов ``set_unfrozen()``.
    * ``get_state_calls`` — счётчик вызовов ``get_state()``.
    """

    state: PayoutFreeze = field(default_factory=PayoutFreeze.unfrozen)
    set_frozen_calls: list[FakePayoutFreezeSetFrozenCall] = field(default_factory=list)
    set_unfrozen_calls: int = 0
    get_state_calls: int = 0

    async def get_state(self) -> PayoutFreeze:
        """Вернуть текущий снапшот."""
        self.get_state_calls += 1
        return self.state

    async def set_frozen(
        self,
        *,
        admin_id: int,
        at: datetime,
        reason: str,
    ) -> PayoutFreeze:
        """Переключить состояние в ``is_frozen=True``.

        Делегирует валидацию атрибутов доменному ``PayoutFreeze.frozen(...)``
        фабричному методу — если ``admin_id <= 0`` / ``at`` naïve /
        ``reason`` пустой, поднимется ``ValueError`` / ``TypeError``.
        """
        self.set_frozen_calls.append(
            FakePayoutFreezeSetFrozenCall(
                admin_id=admin_id,
                at=at,
                reason=reason,
            )
        )
        self.state = PayoutFreeze.frozen(
            admin_id=admin_id,
            at=at,
            reason=reason,
        )
        return self.state

    async def set_unfrozen(self) -> PayoutFreeze:
        """Переключить состояние в ``is_frozen=False``."""
        self.set_unfrozen_calls += 1
        self.state = PayoutFreeze.unfrozen()
        return self.state
