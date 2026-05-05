"""Use-case `InvokeOracle` (Спринт 1.4.B, ГДД §11).

Игрок отправляет `/oracle`. Use-case:

1. Находит `Player` по `tg_id`. Нет — `PlayerNotFoundError`.
2. Считает текущую московскую дату (`IClock.moscow_date()`).
3. Если в `oracle_invocations` уже есть запись на `(player_id,
   moscow_date)` — `OracleAlreadyUsedTodayError` (preflight,
   дешёвая проверка).
4. Достаёт каталог шаблонов нужной локали через
   `IOracleTemplateProvider`.
5. Зовёт чистую `roll_oracle(...)` — выпадает прибавка длины и
   шаблон предсказания.
6. Прибавляет длину (`Player.with_length(length + bonus)`).
7. Сохраняет игрока, добавляет запись в `oracle_invocations`
   (UNIQUE-индекс по `(player_id, moscow_date)` — last-line race-защита).
8. Пишет audit-запись `LENGTH_GRANT` с
   ``idempotency_key=f"oracle:{player_id}:{moscow_date.isoformat()}"``.
   Этот же ключ уникален по своей природе — повтор `/oracle` в тот
   же день уже отбит на шаге 3 / шаге 7.

Транзакция: всё внутри одного `IUnitOfWork`. Любая ошибка откатывает
все мутации (длина, запись истории, audit).

Idempotency-стратегия:
- preflight (шаг 3) и БД-уникальность (шаг 7) защищают от race
  «два `/oracle` одновременно»;
- поле `idempotency_key` в audit отвечает за стабильную аналитику —
  дубликата записи `LENGTH_GRANT/oracle` за день в логе не будет.
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
    Length,
    Player,
)
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IRandom,
    IUnitOfWork,
)
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
        "_audit",
        "_balance",
        "_clock",
        "_history",
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
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._history = history
        self._templates = templates
        self._balance = balance
        self._random = random
        self._audit = audit
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
            new_length = Length(cm=player.length.cm + result.bonus_cm)
            updated = player.with_length(new_length, now=now)
            saved = await self._players.save(updated)

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
                # Race: между preflight и add-ом другой запрос успел
                # вставить запись. БД-UNIQUE отбила вставку — это
                # эквивалент `OracleAlreadyUsedTodayError`.
                raise OracleAlreadyUsedTodayError(
                    player_id=player.id,
                    moscow_date=moscow_date,
                ) from exc

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.LENGTH_GRANT,
                    actor_id=player.tg_id,
                    target_kind="player",
                    target_id=str(player.id),
                    before={"length_cm": player.length.cm},
                    after={"length_cm": saved.length.cm},
                    reason="oracle_invocation",
                    idempotency_key=f"oracle:{player.id}:{moscow_date.isoformat()}",
                    occurred_at=now,
                )
            )

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
