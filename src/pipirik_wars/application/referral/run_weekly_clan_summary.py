"""Use-case `RunWeeklyClanReferralSummary` (Спринт 2.4.E, ГДД §13.3).

APScheduler в воскресенье 18:00 UTC по каждому ACTIVE-клану зовёт
этот use-case. Use-case (внутри одного `IUnitOfWork` для чтения):

1. Резолвит клан по `clan_id` — нет → `IntegrityError` (бывший клан
   удалён, шедулер логирует и идёт дальше).
2. Если `clan.is_frozen` — тихий `return None` (frozen-кланы не
   получают карточек).
3. Выполняет `referrals.weekly_summary_by_clan(clan_id, since, until)`
   с окном «последние 7 суток до момента запуска» (вс. 18:00 UTC →
   с прошлого вс. 18:00 UTC).
4. Если `total == 0` — тихий `return None` (никого не пригласили,
   спам-карточек «итог: 0» не шлём).
5. Иначе резолвит top-3 рефереров через `players.get_by_id(...)`,
   формирует `WeeklyClanReferralSummary` и возвращает шедулеру.
   Шедулер дальше сам зовёт `IWeeklyClanReferralSummaryNotifier.notify(
   summary)` **после** выхода из транзакции.

Окно `[since, until)`: `until` — момент запуска (clock.now() округлён
до секунды), `since = until - timedelta(days=7)`. Полузакрытое окно
гарантирует, что граничный момент `until` не задвоится между двумя
последовательными запусками.

Notifier зовётся **в шедулере**, не здесь — это сохраняет правило
«никакого Telegram I/O внутри транзакции» (ГДД §0.3) и упрощает
тестирование use-case-а: тут чистая логика чтения и формирования DTO.
"""

from __future__ import annotations

from datetime import timedelta

from pipirik_wars.application.dto.inputs import RunWeeklyClanReferralSummaryInput
from pipirik_wars.application.referral.weekly_summary_dto import (
    WeeklyClanReferralEntryDTO,
    WeeklyClanReferralSummary,
)
from pipirik_wars.domain.clan import IClanRepository
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.referral import IReferralRepository
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork
from pipirik_wars.shared.errors import IntegrityError

#: Период агрегации сводки (ровно неделя, ГДД §13.3).
WEEKLY_WINDOW = timedelta(days=7)

#: Сколько рефереров показываем в карточке (`🏆 Топ-3 пригласили...`).
TOP_LIMIT = 3


class RunWeeklyClanReferralSummary:
    """Use-case еженедельной сводки рефералов клана (вс. 18:00 UTC)."""

    __slots__ = ("_clans", "_clock", "_players", "_referrals", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        clans: IClanRepository,
        players: IPlayerRepository,
        referrals: IReferralRepository,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._clans = clans
        self._players = players
        self._referrals = referrals
        self._clock = clock

    async def execute(
        self,
        input_dto: RunWeeklyClanReferralSummaryInput,
    ) -> WeeklyClanReferralSummary | None:
        """Сформировать недельную сводку клана.

        Возвращает:
        - `WeeklyClanReferralSummary` — если за окно был хотя бы один
          новый реферал члена клана;
        - `None` — если клан заморожен или никого не пригласили
          (no-op, шедулер не зовёт notifier).

        :raises IntegrityError: если `clan_id` не найден в `clans`
            (шедулер логирует и продолжает обход остальных кланов).
        """
        until = self._clock.now()
        since = until - WEEKLY_WINDOW

        async with self._uow:
            clan = await self._clans.get_by_id(input_dto.clan_id)
            if clan is None:
                raise IntegrityError(
                    f"clan_id={input_dto.clan_id} not found",
                )
            if clan.is_frozen:
                return None
            assert clan.id is not None

            entries = await self._referrals.weekly_summary_by_clan(
                clan_id=clan.id,
                since=since,
                until=until,
            )
            if not entries:
                return None

            total = sum(entry.count for entry in entries)
            top_entries = entries[:TOP_LIMIT]
            top_dtos: list[WeeklyClanReferralEntryDTO] = []
            for entry in top_entries:
                player = await self._players.get_by_id(player_id=entry.referrer_id)
                if player is None:
                    # Реферер был удалён, но запись `referrals` ещё есть.
                    # Не должно случиться (FK CASCADE в сторону users
                    # обнулит и сами `referrals`), но bias to safe — пропускаем.
                    continue
                top_dtos.append(
                    WeeklyClanReferralEntryDTO(player=player, count=entry.count),
                )

        if not top_dtos:
            return None

        return WeeklyClanReferralSummary(
            clan=clan,
            total=total,
            top=tuple(top_dtos),
        )


__all__ = [
    "TOP_LIMIT",
    "WEEKLY_WINDOW",
    "RunWeeklyClanReferralSummary",
]
