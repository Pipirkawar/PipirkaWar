"""Сущности домена «Клан» (Спринт 1.1, ГДД §1.4 — §1.5).

`Clan` — агрегат, отражающий чат-группу с ботом. Идентифицируется
парой `(id, chat_id)`: внутренний серийный `id` + Telegram-`chat_id`.
`chat_id` может меняться при миграции group → supergroup, но это
редкое событие; `id` стабильный.

`ClanMember` — слабый агрегат «игрок ↔ клан». Один игрок может состоять
ровно в одном клане одновременно (правило ГДД §4: «один игрок — одна
группа за раз»). Уникальность контролируется не VO, а БД-ограничением
+ `IClanMembershipRepository`.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, replace
from datetime import datetime

from pipirik_wars.domain.clan.errors import ClanFrozenError
from pipirik_wars.domain.clan.value_objects import (
    ChatKind,
    ClanStatus,
    ClanTitle,
)


class ClanMemberRole(str, enum.Enum):
    """Роль игрока в клане (ГДД §4 / §5.5).

    `MEMBER` — обычный участник.
    `LEADER` — лидер каравана / атаман разбойников. На уровне Спринта
    1.1 нам важна только сама дискриминация — фактический выбор лидера
    появится в Спринтах 2.1+ (`/caravan_lead`).

    Сюда же позже добавим «глава дня», но это не роль, а отдельная
    сущность с временным интервалом — не путать.
    """

    MEMBER = "member"
    LEADER = "leader"


@dataclass(frozen=True, slots=True)
class Clan:
    """Клан = Telegram-чат с ботом."""

    id: int | None
    chat_id: int
    chat_kind: ChatKind
    title: ClanTitle
    status: ClanStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def new(
        cls,
        *,
        chat_id: int,
        chat_kind: ChatKind,
        title: ClanTitle,
        now: datetime,
    ) -> Clan:
        """Свежезарегистрированный клан (после `my_chat_member: bot added`)."""
        return cls(
            id=None,
            chat_id=chat_id,
            chat_kind=chat_kind,
            title=title,
            status=ClanStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_frozen(self) -> bool:
        return self.status is ClanStatus.FROZEN

    def _ensure_active(self) -> None:
        if self.is_frozen:
            raise ClanFrozenError(chat_id=self.chat_id)

    # ------- мутаторы -------

    def with_title(self, title: ClanTitle, *, now: datetime) -> Clan:
        """Обновить название (админ группы переименовал чат)."""
        self._ensure_active()
        if title == self.title:
            return self
        return replace(self, title=title, updated_at=now)

    def with_chat_id(
        self,
        *,
        new_chat_id: int,
        new_chat_kind: ChatKind,
        now: datetime,
    ) -> Clan:
        """Обработать миграцию group → supergroup (Telegram меняет `chat_id`).

        Этот метод не делает «добавить новый клан» — он именно мигрирует
        существующую запись. Идемпотентность повторного вызова с теми же
        `new_chat_id`/`new_chat_kind` — no-op.
        """
        self._ensure_active()
        if new_chat_id == self.chat_id and new_chat_kind == self.chat_kind:
            return self
        return replace(
            self,
            chat_id=new_chat_id,
            chat_kind=new_chat_kind,
            updated_at=now,
        )

    def freeze(self, *, now: datetime) -> Clan:
        """Заморозить (бот удалён из чата). Идемпотентно: уже frozen — no-op."""
        if self.is_frozen:
            return self
        return replace(self, status=ClanStatus.FROZEN, updated_at=now)

    def unfreeze(self, *, now: datetime) -> Clan:
        """Разморозить (бот добавлен обратно). Идемпотентно."""
        if self.status is ClanStatus.ACTIVE:
            return self
        return replace(self, status=ClanStatus.ACTIVE, updated_at=now)


@dataclass(frozen=True, slots=True)
class ClanMember:
    """Запись о членстве игрока в клане.

    Это «связующий» агрегат-таблица — не агрегат-агрегат: у него нет
    собственного жизненного цикла, кроме «существует / не существует».
    История членств (логика «бывший участник») сохраняется через
    `audit_log`, не в `clan_members`.
    """

    clan_id: int
    player_id: int
    role: ClanMemberRole
    joined_at: datetime

    @classmethod
    def new(
        cls,
        *,
        clan_id: int,
        player_id: int,
        role: ClanMemberRole = ClanMemberRole.MEMBER,
        now: datetime,
    ) -> ClanMember:
        return cls(
            clan_id=clan_id,
            player_id=player_id,
            role=role,
            joined_at=now,
        )

    def with_role(self, role: ClanMemberRole) -> ClanMember:
        if role == self.role:
            return self
        return replace(self, role=role)
