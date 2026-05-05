"""Use-case `InvokeOracle` (Спринты 1.4.B, 1.6.F; ГДД §11, §3.3).

Игрок отправляет `/oracle`. Use-case (всё внутри одного `IUnitOfWork`):

1. Находит `Player` по `tg_id`. Нет — `PlayerNotFoundError`.
2. Считает текущую московскую дату (`IClock.moscow_date()`).
3. Если в `oracle_invocations` уже есть запись на `(player_id,
   moscow_date)` — `OracleAlreadyUsedTodayError` (preflight,
   дешёвая проверка).
4. Достаёт каталог шаблонов нужной локали через
   `IOracleTemplateProvider`.
5. Зовёт чистую `roll_oracle(...)` — выпадает прибавка длины и
   шаблон предсказания.
6. Добавляет запись в `oracle_invocations`
   (UNIQUE-индекс по `(player_id, moscow_date)` — last-line race-защита).
7. Вызывает `ILengthGranter.grant(...)` (`source=ORACLE`,
   `idempotency_key=f"add_length:oracle:{player_id}:{moscow_date}"`).
   Сам `AddLength` проверяет anti-cheat soft-ban, клампит дельту
   по cap-ам, пишет audit `LENGTH_GRANT`, взводит trip-wire при
   превышении (Спринт 1.6.D — `add_length.py`).

Транзакция: всё внутри одного `IUnitOfWork` — «ритуал» (вставка в
`oracle_invocations`) и «прибавка длины» атомарны. `AddLength.grant`
работает в ambient-UoW режиме (Спринт 1.6.F): он не открывает свой
контекст, а только проверяет `uow.is_active` и зовёт репозитории
в сессии вызывающего.

Idempotency-стратегия:
- preflight (шаг 3) и БД-уникальность (шаг 6) защищают от race
  «два `/oracle` одновременно»;
- `idempotency_key` в `AddLength.grant(...)` отвечает за стабильную
  аналитику — дубликата `LENGTH_GRANT` с одним ключом не будет.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pipirik_wars.application.dto.inputs import InvokeOracleInput
from pipirik_wars.application.oracle.templates import IOracleTemplateProvider
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.oracle import (
    IOracleHistoryRepository,
    OracleAlreadyUsedTodayError,
    OracleInvocation,
    OracleResult,
    roll_oracle,
)
from pipirik_wars.domain.player import (
    IPlayerRepository,
    Player,
)
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.shared.ports import (
    IClock,
    IRandom,
    IUnitOfWork,
)
from pipirik_wars.domain.shared.ports.audit import AuditSource
from pipirik_wars.shared.errors import IntegrityError


@dataclass(frozen=True, slots=True)
class OracleInvoked:
    """Результат успешного `/oracle`. Используется bot-handler-ом для
    рендера ответного сообщения «🔮 ... +N см».

    Поля:
    - `result` — выпавший результат (`bonus_cm` + `template`);
    - `player_before` / `player_after` — снимки до/после; handler
      показывает игроку «было N см → стало M см»;
    - `moscow_date` — день, в который записан кулдаун (нужен handler-у
      на случай рендера «вернись завтра»).
    """

    result: OracleResult
    player_before: Player
    player_after: Player
    moscow_date: date


class InvokeOracle:
    """Use-case «получить предсказание и +1..20 см длины»."""

    __slots__ = (
        "_balance",
        "_clock",
        "_history",
        "_length_granter",
        "_players",
        "_random",
        "_templates",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        history: IOracleHistoryRepository,
        templates: IOracleTemplateProvider,
        balance: IBalanceConfig,
        random: IRandom,
        length_granter: ILengthGranter,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._history = history
        self._templates = templates
        self._balance = balance
        self._random = random
        self._length_granter = length_granter
        self._clock = clock

    async def execute(self, input_dto: InvokeOracleInput) -> OracleInvoked:
        """Выполнить `/oracle`. Бросает:

        - `PlayerNotFoundError` — игрока с таким `tg_id` нет в БД;
        - `OracleAlreadyUsedTodayError` — игрок уже звал `/oracle`
          сегодня по Москве (preflight либо БД UNIQUE).
        """
        moscow_date = self._clock.moscow_date()

        async with self._uow:
            player = await self._players.get_by_tg_id(input_dto.tg_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=input_dto.tg_id)
            assert player.id is not None  # repo гарантирует id

            existing = await self._history.get_for_day(
                player_id=player.id,
                moscow_date=moscow_date,
            )
            if existing is not None:
                raise OracleAlreadyUsedTodayError(
                    player_id=player.id,
                    moscow_date=moscow_date,
                )

            cfg = self._balance.get()
            templates = self._templates.get_templates(locale=input_dto.locale)
            result = roll_oracle(
                balance=cfg,
                random=self._random,
                templates=templates,
            )

            now = self._clock.now()

            # 1. Сначала вставка в `oracle_invocations` — last-line race-защита
            # через UNIQUE-индекс; если здесь БД побила «два одновременных
            # /oracle» — выбрасываем бизнес-ошибку, UoW откатывается.
            try:
                await self._history.add(
                    OracleInvocation(
                        player_id=player.id,
                        moscow_date=moscow_date,
                        bonus_cm=result.bonus_cm,
                        template_id=result.template.id,
                        occurred_at=now,
                    )
                )
            except IntegrityError as exc:
                raise OracleAlreadyUsedTodayError(
                    player_id=player.id,
                    moscow_date=moscow_date,
                ) from exc

            # 2. Прибавка длины — через единый ILengthGranter (Спринт 1.6.F).
            # `AddLength` в ambient-UoW режиме проверит anti-cheat soft-ban,
            # клампнет по cap-ам, запишет audit `LENGTH_GRANT` и trip-wire.
            await self._length_granter.grant(
                player_id=player.id,
                delta_cm=result.bonus_cm,
                source=AuditSource.ORACLE,
                reason="oracle_invocation",
                idempotency_key=f"add_length:oracle:{player.id}:{moscow_date.isoformat()}",
            )

            # 3. Перечитываем игрока, чтобы отдать handler-у финальный снапшот
            # (с учётом клампа или полной прибавки).
            saved = await self._players.get_by_id(player_id=player.id) or player

        return OracleInvoked(
            result=result,
            player_before=player,
            player_after=saved,
            moscow_date=moscow_date,
        )


__all__ = [
    "InvokeOracle",
    "OracleInvoked",
]
