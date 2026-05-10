"""In-memory реализация `IPrizeLotRepository` для unit-тестов (Спринт 4.1-C).

Имитирует будущий `SqlAlchemyPrizeLotRepository` (C.3) — генерирует
монотонно-растущие `id`, хранит лоты в `dict[int, PrizeLot]`, проверяет
state-machine при `update_status(...)` через домен.

Использование:

    repo = FakePrizeLotRepository()
    lot = await repo.add(lot=PrizeLot.freshly_generated(...))
    assert lot.id == 1  # id назначен репозиторием

    listed = await repo.list_active(currency=Currency.USDT_DECIMAL)
    assert listed == (lot,)

    reserved = await repo.update_status(
        lot_id=lot.id,
        new_status=PrizeLotStatus.RESERVED,
    )
    assert reserved.status is PrizeLotStatus.RESERVED
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from pipirik_wars.domain.monetization.entities import PrizeLot, PrizeLotStatus
from pipirik_wars.domain.monetization.errors import PrizeLotNotFoundError
from pipirik_wars.domain.monetization.ports import IPrizeLotRepository
from pipirik_wars.domain.monetization.value_objects import Currency


@dataclass
class FakePrizeLotRepository(IPrizeLotRepository):
    """In-memory `IPrizeLotRepository` для тестов use-case-ов.

    Поля:
    - `_storage` — словарь `id -> PrizeLot`. Заполняется через `add(...)`.
    - `_next_id` — следующий `id` для назначения; начинается с `1`.
    - `add_calls` — append-only лог переданных `PrizeLot`-аргументов
      (включая до-add-овый объект без `id`). Полезно для assert-ов
      типа «`add` был вызван с amount=X».
    - `update_status_calls` — append-only лог пар `(lot_id, new_status,
      claimed_at)`. Удобно для проверки идемпотентного отсутствия
      повторных вызовов.
    """

    _storage: dict[int, PrizeLot] = field(default_factory=dict)
    _next_id: int = 1
    add_calls: list[PrizeLot] = field(default_factory=list)
    update_status_calls: list[tuple[int, PrizeLotStatus, datetime | None]] = field(
        default_factory=list
    )

    async def add(self, *, lot: PrizeLot) -> PrizeLot:
        """Назначить `id`, сохранить лот, вернуть копию с проставленным `id`."""
        self.add_calls.append(lot)
        if lot.id is not None:
            assigned_id = lot.id
        else:
            assigned_id = self._next_id
            self._next_id += 1
        stored = replace(lot, id=assigned_id)
        self._storage[assigned_id] = stored
        return stored

    async def get_by_id(self, *, lot_id: int) -> PrizeLot | None:
        """Вернуть лот по `id` или `None` (если не существует)."""
        return self._storage.get(lot_id)

    async def list_active(self, *, currency: Currency) -> Sequence[PrizeLot]:
        """Все `status=ACTIVE`-лоты указанной валюты в порядке `id ASC`."""
        return tuple(
            lot
            for lot_id, lot in sorted(self._storage.items())
            if lot.currency is currency and lot.status is PrizeLotStatus.ACTIVE
        )

    async def update_status(
        self,
        *,
        lot_id: int,
        new_status: PrizeLotStatus,
        claimed_at: datetime | None = None,
    ) -> PrizeLot:
        """Перевести лот в `new_status`, делегируя домену state-machine."""
        self.update_status_calls.append((lot_id, new_status, claimed_at))
        current = self._storage.get(lot_id)
        if current is None:
            raise PrizeLotNotFoundError(lot_id=lot_id)

        if new_status is PrizeLotStatus.RESERVED:
            updated = current.reserve()
        elif new_status is PrizeLotStatus.CLAIMED:
            if claimed_at is None:
                raise ValueError(
                    "FakePrizeLotRepository.update_status: claimed_at is "
                    "required for CLAIMED transition"
                )
            updated = current.claim(claimed_at=claimed_at)
        elif new_status is PrizeLotStatus.REFUNDED:
            updated = current.refund()
        else:
            raise ValueError(
                f"FakePrizeLotRepository.update_status: unsupported new_status={new_status!r}"
            )

        self._storage[lot_id] = updated
        return updated
