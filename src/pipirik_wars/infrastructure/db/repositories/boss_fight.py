"""Реализация `IBossFightRepository` поверх таблицы `boss_fights` (3.3-B).

Сериализация агрегата :class:`BossFight`:

* `boss_fight.kind` (`BossKind`) ↔ строка из CHECK-whitelist-а (`'raid'`).
* `boss_fight.status` (`BossFightStatus`) ↔ строка из CHECK-whitelist-а
  (`'lobby' | 'in_battle' | 'finished' | 'cancelled'`).
* timestamp-поля проходят через `ensure_utc()` — БД может вернуть
  `naive`-datetime для SQLite, `tz-aware` — для Postgres; домен
  всегда работает в UTC.

Все БД-уровневые `IntegrityError`-ы (нарушение CHECK / FK / UNIQUE)
конвертируются в доменный `IntegrityError` из `pipirik_wars.shared.errors`.

Активный рейд для игрока (`get_active_for_player`) ищется в двух
ролях: саммонер/рейдер — через JOIN с `boss_participants`; босс —
через `boss_fights.boss_player_id`. Это даёт полное покрытие
определения «активный» из контракта (`status IN (LOBBY, IN_BATTLE)`).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, exists, or_, select
from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError

from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightStatus,
    BossKind,
    IBossFightRepository,
)
from pipirik_wars.infrastructure.db.models import BossFightORM, BossParticipantORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError

# Статусы, при которых рейд-бой считается «активным» (ещё не завершён,
# ещё не отменён). Используются и в индексах, и в `get_active_for_player`.
_ACTIVE_STATUSES: tuple[str, ...] = (
    BossFightStatus.LOBBY.value,
    BossFightStatus.IN_BATTLE.value,
)


def _row_to_entity(row: BossFightORM) -> BossFight:
    return BossFight(
        id=row.id,
        kind=BossKind(row.kind),
        summoner_player_id=row.summoner_player_id,
        boss_player_id=row.boss_player_id,
        status=BossFightStatus(row.status),
        started_at=ensure_utc(row.started_at),
        lobby_ends_at=ensure_utc(row.lobby_ends_at),
        finished_at=ensure_utc(row.finished_at) if row.finished_at is not None else None,
        random_seed=row.random_seed,
        initial_boss_length_cm=row.initial_boss_length_cm,
        current_boss_length_cm=row.current_boss_length_cm,
        current_round=row.current_round,
    )


class SqlAlchemyBossFightRepository(IBossFightRepository):
    """SQLAlchemy-реализация `IBossFightRepository` (см. domain-port)."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def add(self, boss_fight: BossFight) -> BossFight:
        if boss_fight.id is not None:
            raise DomainIntegrityError(
                f"BossFight with pre-set id={boss_fight.id} cannot be added; use save()"
            )
        row = BossFightORM(
            kind=boss_fight.kind.value,
            summoner_player_id=boss_fight.summoner_player_id,
            boss_player_id=boss_fight.boss_player_id,
            status=boss_fight.status.value,
            started_at=boss_fight.started_at,
            lobby_ends_at=boss_fight.lobby_ends_at,
            finished_at=boss_fight.finished_at,
            random_seed=boss_fight.random_seed,
            initial_boss_length_cm=boss_fight.initial_boss_length_cm,
            current_boss_length_cm=boss_fight.current_boss_length_cm,
            current_round=boss_fight.current_round,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to add boss_fight for summoner_player_id="
                f"{boss_fight.summoner_player_id}: {exc.orig}"
            ) from exc
        return _row_to_entity(row)

    async def get_by_id(self, *, boss_fight_id: int) -> BossFight | None:
        row = await self._uow.session.get(BossFightORM, boss_fight_id)
        if row is None:
            return None
        return _row_to_entity(row)

    async def get_active_for_player(self, *, player_id: int) -> BossFight | None:
        # Игрок может быть в активном рейде в одной из двух ролей:
        # 1) босс — через `boss_fights.boss_player_id`;
        # 2) саммонер/рейдер — через `boss_participants.player_id` JOIN.
        is_raider_subq = (
            select(BossParticipantORM.boss_fight_id)
            .where(BossParticipantORM.player_id == player_id)
            .where(BossParticipantORM.boss_fight_id == BossFightORM.id)
            .correlate(BossFightORM)
        )
        result = await self._uow.session.execute(
            select(BossFightORM)
            .where(BossFightORM.status.in_(_ACTIVE_STATUSES))
            .where(
                or_(
                    BossFightORM.boss_player_id == player_id,
                    exists(is_raider_subq),
                )
            )
            .order_by(desc(BossFightORM.started_at))
            .limit(1),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_entity(row)

    async def get_last_global_started_at(self) -> datetime | None:
        # Время последнего призыва на сервере (для глобального 4-часового
        # кулдауна, ГДД §10.1). Кулдаун стартует с `started_at`,
        # отменённый бой тоже «съедает» окно — поэтому без фильтра
        # по статусу.
        result = await self._uow.session.execute(
            select(BossFightORM.started_at).order_by(desc(BossFightORM.started_at)).limit(1),
        )
        last = result.scalar_one_or_none()
        if last is None:
            return None
        return ensure_utc(last)

    async def save(self, boss_fight: BossFight) -> BossFight:
        if boss_fight.id is None:
            raise DomainIntegrityError("BossFight.save requires id; use add() for new boss fights")
        result = await self._uow.session.execute(
            select(BossFightORM).where(BossFightORM.id == boss_fight.id),
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise DomainIntegrityError(f"BossFight id={boss_fight.id} not found")
        row.kind = boss_fight.kind.value
        row.summoner_player_id = boss_fight.summoner_player_id
        row.boss_player_id = boss_fight.boss_player_id
        row.status = boss_fight.status.value
        row.started_at = boss_fight.started_at
        row.lobby_ends_at = boss_fight.lobby_ends_at
        row.finished_at = boss_fight.finished_at
        row.random_seed = boss_fight.random_seed
        row.initial_boss_length_cm = boss_fight.initial_boss_length_cm
        row.current_boss_length_cm = boss_fight.current_boss_length_cm
        row.current_round = boss_fight.current_round
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to save boss_fight id={boss_fight.id}: {exc.orig}"
            ) from exc
        return _row_to_entity(row)


__all__ = ["SqlAlchemyBossFightRepository"]
