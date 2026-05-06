"""Порт `IClanMassDuelHistoryQuery` (Спринт 2.2.G / ПД 2.2.5).

Запрос «дай мне последние N массовых боёв клана с точки зрения
самого клана» (нашего урона / получ.урона / победы/поражения).
Реализуется напрямую SQL-проекцией над `pvp_mass_duels` без
кэширования (журнал нечасто запрашивается, и каждый бой —
уникальное событие, кэш TTL не даст осмысленного выигрыша).
Отдельный порт нужен, чтобы use-case `GetClanAttackHistory` не
знал про SQL — он просто делегирует запрос.

Аналог `IClanTopQuery` (2.2.A): тонкая read-side абстракция,
которая возвращает доменный VO как DTO для презентера.
"""

from __future__ import annotations

import abc
from collections.abc import Sequence

from pipirik_wars.domain.pvp import ClanMassDuelHistoryEntry


class IClanMassDuelHistoryQuery(abc.ABC):
    """Источник журнала массовых боёв конкретного клана."""

    @abc.abstractmethod
    async def get_recent(
        self,
        *,
        clan_id: int,
        limit: int,
    ) -> Sequence[ClanMassDuelHistoryEntry]:
        """Последние `limit` массовых боёв клана `clan_id`.

        Контракт реализаций:
        - возвращает не более `limit` элементов;
        - элементы упорядочены по убыванию `created_at` (свежие
          сверху), тай-брейкер — `duel_id DESC` (стабильный порядок
          при совпадающих timestamp-ах);
        - в выборку попадают и `COMPLETED`, и `CANCELLED` бои
          (журнал — это полная история, включая отменённые админом);
        - `our_clan_id` каждого entry равен переданному `clan_id`,
          `opponent_clan_id` — другой стороне (clan1 ↔ clan2);
        - если у клана нет ни одного массового боя — возвращает
          пустую последовательность;
        - реализация **не** должна возвращать бои в `IN_PROGRESS`
          (они ещё не закончились — нечего показывать в журнале).
        """
