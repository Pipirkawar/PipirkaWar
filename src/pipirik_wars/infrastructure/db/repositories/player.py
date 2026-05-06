"""Реализация `IPlayerRepository` поверх таблицы `users`."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.player import (
    IPlayerRepository,
    Length,
    Player,
    PlayerAlreadyRegisteredError,
    PlayerName,
    PlayerStatus,
    Thickness,
    Title,
    Username,
)
from pipirik_wars.infrastructure.db.models import UserORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError


def _looks_like_int(value: str) -> bool:
    """`True`, если `value` целиком — целое число (с опциональным `-`)."""
    if not value:
        return False
    body = value[1:] if value[0] in "+-" else value
    return body.isdigit()


def _escape_like(value: str) -> str:
    """Экранирование `%` / `_` / `\\` для безопасного `ILIKE`-поиска (escape='\\')."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row_to_entity(row: UserORM) -> Player:
    created_at: datetime = ensure_utc(row.created_at)
    updated_at: datetime = ensure_utc(row.updated_at)
    anticheat_ban_until: datetime | None = (
        ensure_utc(row.anticheat_ban_until) if row.anticheat_ban_until is not None else None
    )
    return Player(
        id=row.id,
        tg_id=row.tg_id,
        username=Username(value=row.username) if row.username is not None else None,
        length=Length(cm=row.length_cm),
        thickness=Thickness(level=row.thickness_level),
        title=Title(row.title) if row.title is not None else None,
        name=PlayerName(value=row.name) if row.name is not None else None,
        status=PlayerStatus(row.status),
        created_at=created_at,
        updated_at=updated_at,
        locale_override=row.locale_override,
        anticheat_ban_until=anticheat_ban_until,
    )


class SqlAlchemyPlayerRepository(IPlayerRepository):
    """`tg_id` — UNIQUE-индекс; повторный INSERT падает на IntegrityError
    и преобразуется в `PlayerAlreadyRegisteredError`. Все методы
    исполняются внутри активного `SqlAlchemyUnitOfWork`.
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def get_by_tg_id(self, tg_id: int) -> Player | None:
        result = await self._uow.session.execute(
            select(UserORM).where(UserORM.tg_id == tg_id),
        )
        row = result.scalar_one_or_none()
        return _row_to_entity(row) if row is not None else None

    async def get_by_id(self, *, player_id: int) -> Player | None:
        row = await self._uow.session.get(UserORM, player_id)
        return _row_to_entity(row) if row is not None else None

    async def add(self, player: Player) -> Player:
        if player.id is not None:
            raise DomainIntegrityError(
                f"Player with pre-set id={player.id} cannot be added; use save()"
            )
        row = UserORM(
            tg_id=player.tg_id,
            username=player.username.value if player.username is not None else None,
            length_cm=player.length.cm,
            thickness_level=player.thickness.level,
            title=player.title.value if player.title is not None else None,
            name=player.name.value if player.name is not None else None,
            status=player.status.value,
            locale_override=player.locale_override,
            anticheat_ban_until=player.anticheat_ban_until,
            created_at=player.created_at,
            updated_at=player.updated_at,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except IntegrityError as exc:
            raise PlayerAlreadyRegisteredError(tg_id=player.tg_id) from exc
        return _row_to_entity(row)

    async def save(self, player: Player) -> Player:
        if player.id is None:
            raise DomainIntegrityError(
                "Player without id cannot be saved; use add() for new players"
            )
        row = await self._uow.session.get(UserORM, player.id)
        if row is None:
            raise DomainIntegrityError(f"Player id={player.id} does not exist")
        row.username = player.username.value if player.username is not None else None
        row.length_cm = player.length.cm
        row.thickness_level = player.thickness.level
        row.title = player.title.value if player.title is not None else None
        row.name = player.name.value if player.name is not None else None
        row.status = player.status.value
        row.locale_override = player.locale_override
        row.anticheat_ban_until = player.anticheat_ban_until
        row.updated_at = player.updated_at
        # `created_at` намеренно не трогаем — он immutable после INSERT.
        await self._uow.session.flush()
        return _row_to_entity(row)

    async def find_by_query(self, *, query: str, limit: int) -> Sequence[Player]:
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        normalized = query.strip()
        if not normalized:
            return ()

        # 1) Целое число — точный поиск по tg_id (BIGINT, UNIQUE).
        if _looks_like_int(normalized):
            tg_id = int(normalized)
            result = await self._uow.session.execute(
                select(UserORM).where(UserORM.tg_id == tg_id),
            )
            row = result.scalar_one_or_none()
            return (_row_to_entity(row),) if row is not None else ()

        # 2) `@username` — точный по `users.username` (без `@`).
        if normalized.startswith("@") and len(normalized) > 1:
            username_value = normalized[1:]
            result = await self._uow.session.execute(
                select(UserORM).where(UserORM.username == username_value),
            )
            row = result.scalar_one_or_none()
            return (_row_to_entity(row),) if row is not None else ()

        # 3) Свободный текст → ILIKE %query% по `username` и `name`.
        # `escape='\\'` защищает от пользовательских `%` / `_` в подстроке.
        like_pattern = f"%{_escape_like(normalized)}%"
        stmt = (
            select(UserORM)
            .where(
                or_(
                    UserORM.username.ilike(like_pattern, escape="\\"),
                    UserORM.name.ilike(like_pattern, escape="\\"),
                ),
            )
            .order_by(UserORM.id.asc())
            .limit(limit)
        )
        result = await self._uow.session.execute(stmt)
        return tuple(_row_to_entity(row) for row in result.scalars().all())

    async def list_top_by_length(self, *, limit: int) -> Sequence[Player]:
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        # Только ACTIVE: замороженные игроки не должны светиться в `/top`.
        # Тай-брейкер `id ASC` — стабильный порядок, чтобы кэш не мерцал.
        stmt = (
            select(UserORM)
            .where(UserORM.status == PlayerStatus.ACTIVE.value)
            .order_by(UserORM.length_cm.desc(), UserORM.id.asc())
            .limit(limit)
        )
        result = await self._uow.session.execute(stmt)
        return tuple(_row_to_entity(row) for row in result.scalars().all())
