"""Use-case `GetProfile` (Спринт 1.1.9, ГДД §2.2).

Возвращает данные карточки игрока: сам `Player` (из БД) + его
текущее «название» (`DisplayName`), вычисленное по длине через
`IBalanceConfig`. Никаких мутаций — операция read-only, audit-запись
не пишется.

Acceptance из Спринта 1.1.9 (development_plan.md):
> Карточка рендерится 1-в-1, ник в формате «Титул Название Имя»;
> новичок без титула/имени отображается просто как «Пипирик».

Use-case **не** рендерит текст — это работа `bot/presenters/profile.py`.
Здесь мы только собираем доменные данные, чтобы presenter был
полностью отделён от инфраструктуры (БД + балансовый источник).

`get_by_tg_id` репозитория уже завернут в активный UoW (см.
`SqlAlchemyPlayerRepository`), поэтому здесь явный `async with self._uow`
тоже нужен — чтобы read-консистентно (single transaction) получить
снимок и не зависеть от внешнего управления транзакцией.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.balance import IBalanceConfig
from pipirik_wars.domain.player import (
    DisplayName,
    IPlayerRepository,
    Player,
)
from pipirik_wars.domain.shared.ports import IUnitOfWork


@dataclass(frozen=True, slots=True)
class ProfileView:
    """Снимок карточки персонажа.

    `display_name` — рассчитан в момент запроса по `player.length` через
    `IBalanceConfig.display_name_for(...)`. Если позже балансовая
    таблица перечитается (`/balance_reload`), `display_name` для тех же
    значений длины может смениться — следующий вызов `GetProfile`
    отдаст уже новое название.
    """

    player: Player
    display_name: DisplayName


class GetProfile:
    """Use-case чтения карточки игрока."""

    __slots__ = ("_balance", "_players", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        balance: IBalanceConfig,
    ) -> None:
        self._uow = uow
        self._players = players
        self._balance = balance

    async def execute(self, *, tg_id: int) -> ProfileView | None:
        """Найти игрока по `tg_id` и собрать `ProfileView`.

        Возвращает `None`, если игрок не зарегистрирован в боте —
        handler покажет пользователю инструкцию «нажмите /start».
        """
        async with self._uow:
            player = await self._players.get_by_tg_id(tg_id)
            if player is None:
                return None
            display_name = DisplayName(
                value=self._balance.get().display_name_for(player.length.cm),
            )
            return ProfileView(player=player, display_name=display_name)
