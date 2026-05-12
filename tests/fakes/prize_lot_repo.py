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
from pipirik_wars.domain.monetization.errors import (
    PrizeLotNotFoundError,
    PrizeLotStatusTransitionError,
)
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
    # Side-map lot_id -> player_id (winner). Заполняется тестами через
    # `record_winner(...)` (т.к. PrizeLot-агрегат до шага E.11
    # не хранит winner_id; в E.11 это станет полем в схеме).
    winners: dict[int, int] = field(default_factory=dict)
    add_calls: list[PrizeLot] = field(default_factory=list)
    update_status_calls: list[tuple[int, PrizeLotStatus, datetime | None, datetime | None]] = field(
        default_factory=list
    )
    # C.6.d test hook: при `True` `update_status` **до** изменения хранилища
    # выкидывает `PrizeLotStatusTransitionError` (имитация race-condition,
    # когда другой игрок забронировал лот первым между `list_active()` и
    # `update_status()`). Use-case обязан подменить outcome на LengthGain.
    raise_status_transition_on_update: bool = False

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
        reserved_at: datetime | None = None,
        claimed_at: datetime | None = None,
    ) -> PrizeLot:
        """Перевести лот в `new_status`, делегируя домену state-machine."""
        self.update_status_calls.append((lot_id, new_status, reserved_at, claimed_at))
        current = self._storage.get(lot_id)
        if current is None:
            raise PrizeLotNotFoundError(lot_id=lot_id)
        if self.raise_status_transition_on_update:
            raise PrizeLotStatusTransitionError(
                lot_id=lot_id,
                from_status=current.status,
                to_status=new_status,
            )

        if new_status is PrizeLotStatus.RESERVED:
            if reserved_at is None:
                raise ValueError(
                    "FakePrizeLotRepository.update_status: reserved_at is "
                    "required for RESERVED transition"
                )
            updated = current.reserve(reserved_at=reserved_at)
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

    def record_winner(self, *, lot_id: int, player_id: int) -> None:
        """Связать CLAIMED-лот с winner-игроком в in-memory хранилище.

        Используется тестами `EvaluatePayoutLimit` use-case-а (E.6) и
        будущими `ClaimPrize`-тестами (E.10), чтобы записать
        кто заклеймил лот. До шага E.11 PrizeLot-агрегат не хранит
        winner_id — храним в sidemap `winners`. Валидирует:
        `lot_id` в `_storage`, статус лота == CLAIMED, `player_id > 0`.
        """
        if player_id <= 0:
            raise ValueError(
                f"FakePrizeLotRepository.record_winner: player_id must be > 0, got {player_id}"
            )
        lot = self._storage.get(lot_id)
        if lot is None:
            raise PrizeLotNotFoundError(lot_id=lot_id)
        if lot.status is not PrizeLotStatus.CLAIMED:
            raise ValueError(
                f"FakePrizeLotRepository.record_winner: lot {lot_id} status "
                f"is {lot.status.value!r}, expected 'claimed'"
            )
        self.winners[lot_id] = player_id

    async def sum_claimed_in_window(
        self,
        *,
        player_id: int,
        currency: Currency,
        since: datetime,
    ) -> int:
        """Сумма `amount_native` CLAIMED-лотов игрока в окне (ин-memory).

        Линейный проход по `_storage` + `winners`. В SQL-реализации (E.11)
        будет покрывающий индекс `(winner_id, currency, status, claimed_at)`.
        """
        total = 0
        for lot_id, lot in self._storage.items():
            if lot.status is not PrizeLotStatus.CLAIMED:
                continue
            if lot.currency is not currency:
                continue
            if lot.claimed_at is None or lot.claimed_at < since:
                continue
            if self.winners.get(lot_id) != player_id:
                continue
            total += lot.amount_native
        return total

    async def oldest_claimed_at_in_window(
        self,
        *,
        player_id: int,
        currency: Currency,
        since: datetime,
    ) -> datetime | None:
        """Самый ранний `claimed_at` для player+currency в окне или `None`."""
        candidates: list[datetime] = []
        for lot_id, lot in self._storage.items():
            if lot.status is not PrizeLotStatus.CLAIMED:
                continue
            if lot.currency is not currency:
                continue
            if lot.claimed_at is None or lot.claimed_at < since:
                continue
            if self.winners.get(lot_id) != player_id:
                continue
            candidates.append(lot.claimed_at)
        if not candidates:
            return None
        return min(candidates)

    async def list_expired_reserved(
        self,
        *,
        currency: Currency,
        expired_before: datetime,
        limit: int = 100,
    ) -> Sequence[PrizeLot]:
        """Все `RESERVED`-лоты `currency` с `reserved_at <= expired_before`.

        Порядок — `ORDER BY reserved_at ASC, id ASC` (самые старые вперёд).
        `limit` обрезает результат после сортировки.
        """
        candidates = [
            lot
            for lot in self._storage.values()
            if lot.currency is currency
            and lot.status is PrizeLotStatus.RESERVED
            and lot.reserved_at is not None
            and lot.reserved_at <= expired_before
        ]

        def _sort_key(lot: PrizeLot) -> tuple[datetime, int]:
            assert lot.reserved_at is not None  # filtered above
            assert lot.id is not None  # add(...) assigns id before storage
            return (lot.reserved_at, lot.id)

        candidates.sort(key=_sort_key)
        return tuple(candidates[:limit])
