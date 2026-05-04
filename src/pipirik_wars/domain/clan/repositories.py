"""Репозитории кланов (порты)."""

from __future__ import annotations

import abc
from collections.abc import Sequence

from pipirik_wars.domain.clan.entities import Clan, ClanMember


class IClanRepository(abc.ABC):
    """Доступ к таблице `clans`. Все вызовы — внутри активного UoW."""

    @abc.abstractmethod
    async def get_by_chat_id(self, chat_id: int) -> Clan | None:
        """Найти клан по текущему `chat_id`. None — если такого чата нет."""

    @abc.abstractmethod
    async def get_by_id(self, clan_id: int) -> Clan | None:
        """Найти клан по внутреннему `id`. None — если такого клана нет."""

    @abc.abstractmethod
    async def add(self, clan: Clan) -> Clan:
        """Добавить новый клан. Возвращает копию с проставленным `id`.

        Для уже существующего `chat_id` бросает
        `ClanAlreadyRegisteredError`.
        """

    @abc.abstractmethod
    async def save(self, clan: Clan) -> Clan:
        """Обновить запись по `id`.

        Для несуществующего `id` бросает `IntegrityError`.
        """


class IClanMembershipRepository(abc.ABC):
    """Доступ к таблице `clan_members`. Внутри активного UoW."""

    @abc.abstractmethod
    async def get_by_player(self, player_id: int) -> ClanMember | None:
        """Текущее (единственное) членство игрока. None — если игрок не в клане."""

    @abc.abstractmethod
    async def list_by_clan(self, clan_id: int) -> Sequence[ClanMember]:
        """Все участники клана. Порядок — стабильный (`joined_at ASC`)."""

    @abc.abstractmethod
    async def add(self, member: ClanMember) -> ClanMember:
        """Создать запись. Дубль `(clan_id, player_id)` →
        `ClanMembershipExistsError`.
        """

    @abc.abstractmethod
    async def remove(self, *, clan_id: int, player_id: int) -> bool:
        """Удалить членство. Возвращает True, если запись была.

        Никаких исключений на «не существовало» — этот метод
        идемпотентный (для случаев, когда игрок ушёл из чата
        несколько раз подряд / Telegram прислал дубль `chat_member`).
        """
