"""Реализация `IRouletteSpinRepository` поверх таблицы `roulette_spins` (Спринт 3.5-B).

Append-only event-log free-to-play рулетки. Каждая прокрутка — отдельная
строка; UPDATE-ов нет. Идемпотентность гарантируется на уровне БД через
уникальный индекс по `idempotency_key` + диалект-специфичный
`INSERT ... ON CONFLICT (idempotency_key) DO NOTHING` (Postgres /
SQLite одинаково).

`record(...)` — вставляет одну прокрутку. Повторный вызов с тем же
ключом — no-op.
`last_free_spin_at(player_id)` — возвращает момент последней прокрутки
этого игрока (`MAX(occurred_at)`) или `None`. Используется
`SpinFreeRoulette`-use-case-ом 3.5-C для anti-cheat-cooldown.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import Insert as PgInsert, insert as pg_insert
from sqlalchemy.dialects.sqlite import Insert as SqliteInsert, insert as sqlite_insert
from sqlalchemy.sql.dml import Insert as DialectInsert

from pipirik_wars.domain.roulette import IRouletteSpinRepository, RouletteSpin
from pipirik_wars.infrastructure.db.models import RouletteSpinORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyRouletteSpinRepository(IRouletteSpinRepository):
    """Репозиторий event-log-а рулетки поверх `roulette_spins`-таблицы."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def record(self, *, spin: RouletteSpin) -> None:
        session = self._uow.session
        dialect = session.bind.dialect.name if session.bind is not None else ""
        values = {
            "player_id": spin.player_id,
            "occurred_at": spin.occurred_at,
            "kind": spin.kind.value,
            "length_cm": spin.length_cm,
            "idempotency_key": spin.idempotency_key,
        }
        stmt: DialectInsert
        if dialect == "postgresql":
            pg_stmt: PgInsert = pg_insert(RouletteSpinORM).values(values)
            stmt = pg_stmt.on_conflict_do_nothing(
                index_elements=[RouletteSpinORM.idempotency_key],
            )
        else:
            # SQLite (тесты) — синтаксис тот же, но через свой диалект.
            sl_stmt: SqliteInsert = sqlite_insert(RouletteSpinORM).values(values)
            stmt = sl_stmt.on_conflict_do_nothing(
                index_elements=[RouletteSpinORM.idempotency_key],
            )
        await session.execute(stmt)

    async def last_free_spin_at(self, *, player_id: int) -> datetime | None:
        stmt = select(func.max(RouletteSpinORM.occurred_at)).where(
            RouletteSpinORM.player_id == player_id,
        )
        result = await self._uow.session.execute(stmt)
        last = result.scalar_one_or_none()
        if last is None:
            return None
        # SQLAlchemy + aiosqlite возвращает naïve-datetime для
        # `DateTime(timezone=True)`-колонок (это драйверный квирк
        # SQLite — он не хранит TZ-инфу). Postgres вернёт TZ-aware.
        # Чтобы тесты (SQLite) получали стабильный TZ-aware результат,
        # мы НЕ навязываем UTC здесь — оставляем как драйвер вернул;
        # доменный VO `RouletteSpin.__post_init__` гарантирует, что
        # на запись приходит TZ-aware (запись остаётся консистентной).
        # Чтение применяется как «последний момент» — потребитель в
        # 3.5-C сравнивает с `now` и ему хватит локального
        # упорядочивания. Подробнее — в README интеграционных тестов.
        return last
