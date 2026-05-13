"""Репозитории кланов (порты)."""

from __future__ import annotations

import abc
from collections.abc import Sequence

from pipirik_wars.domain.clan.entities import Clan, ClanMember
from pipirik_wars.domain.clan.top_entry import ClanTopEntry
from pipirik_wars.domain.clan.value_objects import ClanStatus


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

    @abc.abstractmethod
    async def list_top_by_total_length(self, *, limit: int) -> Sequence[ClanTopEntry]:
        """Топ-`limit` кланов по сумме длин активных участников (ПД 2.2.1).

        Контракт реализаций:
        - возвращает не более `limit` элементов;
        - элементы упорядочены по убыванию `total_length_cm`,
          тай-брейкер — `clan_id ASC` (стабильный порядок);
        - в выборке только `ClanStatus.ACTIVE`-кланы и только
          `PlayerStatus.ACTIVE`-игроки;
        - кланы без активных участников **исключаются** (sum=0,
          count=0 не интересен ГДД §6 — топ показывает «живые» кланы).
        """

    @abc.abstractmethod
    async def list_active(self) -> Sequence[Clan]:
        """Список всех `ClanStatus.ACTIVE`-кланов (Спринт 2.3.F.2).

        Используется cron-шедулером «Главы клана дня» при старте бота
        и при ежесуточном перепланировании: для каждого активного клана
        регистрируется отдельная APScheduler-задача со случайным
        offset-ом 0..24h от 00:00 МСК. Frozen-кланы пропускаются — они
        и так получили бы no-op в `RunDailyHeadCron`, лучше не плодить
        мёртвые job-ы.

        Контракт реализаций:
        - возвращает все клиенты `ClanStatus.ACTIVE`;
        - порядок стабильный — `clan_id ASC` (для детерминизма
          per-clan offset-а в логах / тестах);
        - frozen-кланы исключаются (см. выше).
        """

    @abc.abstractmethod
    async def list_all(
        self,
        *,
        status_filter: ClanStatus | None = None,
        limit: int,
        offset: int = 0,
    ) -> Sequence[Clan]:
        """Paginated list of clans with optional status filter (Sprint 4.5-E).

        Used by admin web panel for the "Clans" section.

        Contract:
        - if ``status_filter`` is ``None``, returns all clans;
        - otherwise returns only clans with matching ``status``;
        - ordered by ``id ASC`` (stable);
        - ``offset`` / ``limit`` for pagination.
        """

    @abc.abstractmethod
    async def count_all(self, *, status_filter: ClanStatus | None = None) -> int:
        """Total count of clans matching optional status filter (Sprint 4.5-E)."""

    @abc.abstractmethod
    async def count_active_for_player(
        self,
        *,
        player_id: int,
        min_tribe_size: int,
    ) -> int:
        """Количество активных племён, в которых состоит игрок (ГДД §11.1, Спринт 3.6-A).

        Используется use-case-ом `InvokeOracle` для расчёта «бонус-за-племена»
        (`+cm_per_tribe` за каждое квалифицированное племя, кап `cap_cm`).

        «Активное племя» = клан, удовлетворяющий ВСЕМ условиям одновременно:
        - `Clan.status == ClanStatus.ACTIVE` (frozen-кланы исключены);
        - игрок состоит в `clan_members` этого клана (`player_id`);
        - общее число `clan_members.player_id` в этом клане **больше или
          равно** `min_tribe_size` (включая самого игрока). Это отсекает
          «карликовые» племена, созданные ради бонуса; пороговое значение
          задаётся балансом (`OracleConfig.tribe_bonus.min_tribe_size`,
          дефолт `4`, ГДД §11.1).

        Контракт реализаций:
        - возвращает `0` для несуществующего игрока, для frozen-племён,
          для слишком маленьких (`< min_tribe_size`) и для тех, где игрок
          **не** является членом;
        - `min_tribe_size >= 1` — если меньше, поведение не определено
          (валидируется на уровне pydantic-конфига перед вызовом);
        - агрегация — read-only, без побочных эффектов.

        В Фазе 3 (один игрок ↔ один клан, ГДД §4) результат всегда `0` или
        `1`. Метод заложен с `int`-результатом на будущее «несколько племён»
        (Фаза 4+), чтобы не менять сигнатуру: cap `cap_cm` уже встроен в
        конфиг, а домен и хранилище не меняются.
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
