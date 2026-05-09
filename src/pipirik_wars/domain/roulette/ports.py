"""Порты слоя «Free-to-play рулетка» (Спринт 3.5-B).

Контракт чистый: репозиторий **не** видит ORM, не видит SQL — он
принимает доменные значения (`player_id: int`, `RouletteSpin`-VO,
`now: datetime`) и работает только в терминах домена. Use-case
`SpinFreeRoulette` (Спринт 3.5-C) пользуется только этим портом и
не знает про SQLAlchemy / Alembic.

`IRouletteSpinRepository`:

* `record(*, spin)` — append-only запись одной прокрутки в event-log.
  Идемпотентность по `spin.idempotency_key` (повтор `record(...)` с
  тем же ключом — no-op, без ошибки). Это страхует use-case от
  двойного клика `[Прокрутить]`-кнопки в боте.
* `last_free_spin_at(*, player_id)` — момент последней прокрутки
  игрока (для будущей anti-cheat-проверки cooldown в 3.5-C, если
  потребуется); возвращает `None`, если игрок никогда не прокручивал.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pipirik_wars.domain.roulette.entities import RouletteSpin

__all__ = [
    "IRouletteSpinRepository",
]


class IRouletteSpinRepository(Protocol):
    """Репозиторий event-log-а прокруток free-to-play рулетки (Спринт 3.5-B).

    Все методы — асинхронные, выполняются в открытой `IUnitOfWork`-сессии.
    Композиционный root (`bot/main.py`) пробрасывает SQLAlchemy-impl;
    тесты use-case-ов (Спринт 3.5-C) — `FakeRouletteSpinRepository`.

    Семантика записей — append-only: каждая прокрутка — отдельная строка,
    никаких UPDATE-ов. Гарантия дедупликации — на уровне БД-индекса
    `UNIQUE(idempotency_key)`; повторный `record(...)` с тем же ключом
    тихо игнорируется (см. `record`-docstring).
    """

    async def record(self, *, spin: RouletteSpin) -> None:
        """Записать одну прокрутку в `roulette_spins` (append-only, idempotent).

        При повторном вызове с `spin.idempotency_key`, который уже есть
        в `roulette_spins`, метод возвращает `None` без побочных
        эффектов (БД-уровневая идемпотентность через
        `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING`).
        Это значит use-case `SpinFreeRoulette` может безопасно вызвать
        `record(...)` повторно при retry-е — лишней строки в БД
        не появится.

        ⚠️ Идемпотентность только по `idempotency_key`. Если вызывающий
        код передаст две **разные** прокрутки с одним ключом —
        запишется первая, вторая будет тихо проглочена. Поэтому ключ
        обязан быть детерминированным относительно бизнес-намерения
        (например, `f"roulette_free:{player_id}:{tg_message_id}"`).

        Поднимает `pipirik_wars.shared.errors.IntegrityError`, если
        `spin.player_id` ссылается на несуществующего игрока (FK
        violation). Это сигнал бага — use-case обязан гарантировать
        существование игрока до вызова `record(...)`.
        """
        ...

    async def last_free_spin_at(self, *, player_id: int) -> datetime | None:
        """Момент последней прокрутки игрока (TZ-aware) или `None`.

        Используется для anti-cheat-проверки cooldown-а в use-case-е
        `SpinFreeRoulette` (Спринт 3.5-C, если ГДД §12.4 потребует
        такого ограничения). Не падает при отсутствии записей —
        возвращает `None`, и вызывающий код сам решает, считать ли
        это «можно крутить» или «впервые крутить» (для cooldown-а
        обычно `None` ⇒ «никаких ограничений»).

        Реализуется через `SELECT MAX(occurred_at) FROM roulette_spins
        WHERE player_id = :player_id` (B-tree индекс по
        `(player_id, occurred_at DESC)` — см. ORM-таблицу).
        """
        ...
