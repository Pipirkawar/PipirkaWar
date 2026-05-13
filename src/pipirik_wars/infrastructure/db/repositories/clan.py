"""Реализации `IClanRepository` и `IClanMembershipRepository`."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanAlreadyRegisteredError,
    ClanMember,
    ClanMemberRole,
    ClanMembershipExistsError,
    ClanStatus,
    ClanTitle,
    ClanTopEntry,
    IClanMembershipRepository,
    IClanRepository,
)
from pipirik_wars.domain.player import PlayerStatus
from pipirik_wars.infrastructure.db.models import ClanMemberORM, ClanORM, UserORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError


def _row_to_clan(row: ClanORM) -> Clan:
    return Clan(
        id=row.id,
        chat_id=row.chat_id,
        chat_kind=ChatKind(row.chat_kind),
        title=ClanTitle(value=row.title),
        status=ClanStatus(row.status),
        created_at=ensure_utc(row.created_at),
        updated_at=ensure_utc(row.updated_at),
    )


def _row_to_member(row: ClanMemberORM) -> ClanMember:
    return ClanMember(
        clan_id=row.clan_id,
        player_id=row.player_id,
        role=ClanMemberRole(row.role),
        joined_at=ensure_utc(row.joined_at),
    )


class SqlAlchemyClanRepository(IClanRepository):
    """`chat_id` — UNIQUE; дубль INSERT даёт `ClanAlreadyRegisteredError`."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def get_by_chat_id(self, chat_id: int) -> Clan | None:
        result = await self._uow.session.execute(
            select(ClanORM).where(ClanORM.chat_id == chat_id),
        )
        row = result.scalar_one_or_none()
        return _row_to_clan(row) if row is not None else None

    async def get_by_id(self, clan_id: int) -> Clan | None:
        row = await self._uow.session.get(ClanORM, clan_id)
        return _row_to_clan(row) if row is not None else None

    async def add(self, clan: Clan) -> Clan:
        if clan.id is not None:
            raise DomainIntegrityError(
                f"Clan with pre-set id={clan.id} cannot be added; use save()"
            )
        row = ClanORM(
            chat_id=clan.chat_id,
            chat_kind=clan.chat_kind.value,
            title=clan.title.value,
            status=clan.status.value,
            created_at=clan.created_at,
            updated_at=clan.updated_at,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except IntegrityError as exc:
            raise ClanAlreadyRegisteredError(chat_id=clan.chat_id) from exc
        return _row_to_clan(row)

    async def save(self, clan: Clan) -> Clan:
        if clan.id is None:
            raise DomainIntegrityError("Clan without id cannot be saved; use add() for new clans")
        row = await self._uow.session.get(ClanORM, clan.id)
        if row is None:
            raise DomainIntegrityError(f"Clan id={clan.id} does not exist")
        row.chat_id = clan.chat_id
        row.chat_kind = clan.chat_kind.value
        row.title = clan.title.value
        row.status = clan.status.value
        row.updated_at = clan.updated_at
        try:
            await self._uow.session.flush()
        except IntegrityError as exc:
            # Может вылететь, если `with_chat_id` мигрировал на занятый chat_id.
            raise ClanAlreadyRegisteredError(chat_id=clan.chat_id) from exc
        return _row_to_clan(row)

    async def list_top_by_total_length(self, *, limit: int) -> Sequence[ClanTopEntry]:
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        # Топ кланов по сумме длин ACTIVE-участников (Спринт 2.2.A / ПД 2.2.1).
        # INNER JOIN clan_members → users отсеивает «осиротевшие» записи
        # на уровне БД; WHERE отсекает frozen-кланов и не-active игроков;
        # GROUP BY по `clans.id`/`clans.title` (PostgreSQL: title должен быть в
        # GROUP BY либо в агрегате — берём в GROUP BY, чтобы не зависеть от
        # `functional dependency` диалекта). Сорт: по сумме DESC, тай-брейкер
        # `clans.id ASC` — стабильный порядок.
        total_length = func.coalesce(func.sum(UserORM.length_cm), 0).label("total_length_cm")
        member_count = func.count(UserORM.id).label("member_count")
        stmt = (
            select(
                ClanORM.id,
                ClanORM.title,
                total_length,
                member_count,
            )
            .join(ClanMemberORM, ClanMemberORM.clan_id == ClanORM.id)
            .join(UserORM, UserORM.id == ClanMemberORM.player_id)
            .where(
                ClanORM.status == ClanStatus.ACTIVE.value,
                UserORM.status == PlayerStatus.ACTIVE.value,
            )
            .group_by(ClanORM.id, ClanORM.title)
            .order_by(total_length.desc(), ClanORM.id.asc())
            .limit(limit)
        )
        result = await self._uow.session.execute(stmt)
        return tuple(
            ClanTopEntry(
                clan_id=row.id,
                clan_title=ClanTitle(value=row.title),
                total_length_cm=int(row.total_length_cm),
                member_count=int(row.member_count),
            )
            for row in result.all()
        )

    async def list_active(self) -> Sequence[Clan]:
        # Список ACTIVE-кланов для cron-шедулера «Главы клана дня»
        # (Спринт 2.3.F.2). Стабильный порядок `clans.id ASC` — нужен
        # детерминизм per-clan offset-а в логах / тестах.
        stmt = (
            select(ClanORM)
            .where(ClanORM.status == ClanStatus.ACTIVE.value)
            .order_by(ClanORM.id.asc())
        )
        result = await self._uow.session.execute(stmt)
        return tuple(_row_to_clan(row) for row in result.scalars().all())

    async def list_all(
        self,
        *,
        status_filter: ClanStatus | None = None,
        limit: int,
        offset: int = 0,
    ) -> Sequence[Clan]:
        stmt = select(ClanORM).order_by(ClanORM.id.asc())
        if status_filter is not None:
            stmt = stmt.where(ClanORM.status == status_filter.value)
        stmt = stmt.offset(offset).limit(limit)
        result = await self._uow.session.execute(stmt)
        return tuple(_row_to_clan(row) for row in result.scalars().all())

    async def count_all(self, *, status_filter: ClanStatus | None = None) -> int:
        stmt = select(func.count(ClanORM.id))
        if status_filter is not None:
            stmt = stmt.where(ClanORM.status == status_filter.value)
        result = await self._uow.session.execute(stmt)
        return int(result.scalar_one())

    async def count_active_for_player(
        self,
        *,
        player_id: int,
        min_tribe_size: int,
    ) -> int:
        # Бонус-за-племена (ГДД §11.1, Спринт 3.6-A): количество активных
        # кланов, в которых состоит игрок, и где общее число `clan_members`
        # >= `min_tribe_size`. Frozen-кланы исключены.
        #
        # Реализация:
        #   1) подзапрос `member_clan_ids` — id кланов, где есть данный игрок;
        #   2) внешний `select` по `clan_members` × `clans` отфильтровывает
        #      ACTIVE-кланы из этого списка и группирует по clan_id, оставляя
        #      только те, где `COUNT(*) >= min_tribe_size`;
        #   3) количество строк после `HAVING` — искомый ответ.
        #
        # Метод ничего не пишет, не открывает транзакций; вызывается из
        # use-case-а внутри ambient-UoW.
        if min_tribe_size < 1:
            raise ValueError(f"min_tribe_size must be >= 1, got {min_tribe_size}")

        member_clan_ids = (
            select(ClanMemberORM.clan_id)
            .where(ClanMemberORM.player_id == player_id)
            .scalar_subquery()
        )
        stmt = (
            select(ClanMemberORM.clan_id)
            .join(ClanORM, ClanORM.id == ClanMemberORM.clan_id)
            .where(
                ClanMemberORM.clan_id.in_(member_clan_ids),
                ClanORM.status == ClanStatus.ACTIVE.value,
            )
            .group_by(ClanMemberORM.clan_id)
            .having(func.count(ClanMemberORM.player_id) >= min_tribe_size)
        )
        result = await self._uow.session.execute(stmt)
        return len(result.all())


class SqlAlchemyClanMembershipRepository(IClanMembershipRepository):
    """`UNIQUE(player_id)` гарантирует «один игрок = один клан».

    Дубль `(clan_id, player_id)` или нарушение `UNIQUE(player_id)`
    превращается в `ClanMembershipExistsError`.
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def get_by_player(self, player_id: int) -> ClanMember | None:
        result = await self._uow.session.execute(
            select(ClanMemberORM).where(ClanMemberORM.player_id == player_id),
        )
        row = result.scalar_one_or_none()
        return _row_to_member(row) if row is not None else None

    async def list_by_clan(self, clan_id: int) -> Sequence[ClanMember]:
        result = await self._uow.session.execute(
            select(ClanMemberORM)
            .where(ClanMemberORM.clan_id == clan_id)
            .order_by(ClanMemberORM.joined_at.asc()),
        )
        return [_row_to_member(row) for row in result.scalars().all()]

    async def add(self, member: ClanMember) -> ClanMember:
        row = ClanMemberORM(
            clan_id=member.clan_id,
            player_id=member.player_id,
            role=member.role.value,
            joined_at=member.joined_at,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except IntegrityError as exc:
            raise ClanMembershipExistsError(
                clan_id=member.clan_id,
                player_id=member.player_id,
            ) from exc
        return _row_to_member(row)

    async def remove(self, *, clan_id: int, player_id: int) -> bool:
        result = await self._uow.session.execute(
            delete(ClanMemberORM).where(
                ClanMemberORM.clan_id == clan_id,
                ClanMemberORM.player_id == player_id,
            ),
        )
        # DELETE возвращает CursorResult; защищаемся от изменений API.
        if not isinstance(result, CursorResult):  # pragma: no cover
            raise RuntimeError("DELETE must return CursorResult")
        return bool(result.rowcount and result.rowcount > 0)
