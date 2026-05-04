"""Реализации `IClanRepository` и `IClanMembershipRepository`."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import CursorResult, delete, select
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
    IClanMembershipRepository,
    IClanRepository,
)
from pipirik_wars.infrastructure.db.models import ClanMemberORM, ClanORM
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
