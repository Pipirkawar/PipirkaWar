"""Use-case `InvokeOracle` (Спринты 1.4.B, 1.6.F, 3.6-A; ГДД §11, §11.1, §3.3).

Игрок отправляет `/oracle`. Use-case (всё внутри одного `IUnitOfWork`):

1. Находит `Player` по `tg_id`. Нет — `PlayerNotFoundError`.
2. Считает текущую московскую дату (`IClock.moscow_date()`).
3. Если в `oracle_invocations` уже есть запись на `(player_id,
   moscow_date)` — `OracleAlreadyUsedTodayError` (preflight,
   дешёвая проверка).
4. Достаёт каталог шаблонов нужной локали через
   `IOracleTemplateProvider`.
5. Зовёт чистую `roll_oracle(...)` — выпадает базовая прибавка
   длины (`base_cm`) и шаблон предсказания.
6. **Спринт 3.6-A (ГДД §11.1):** если `oracle.tribe_bonus.enabled`,
   считает `n_active = clans.count_active_for_player(...)` и
   `tribe_bonus_cm = min(n_active * cm_per_tribe, cap_cm)`. При
   `enabled=false` подсчёт не делаем (`n_active = 0`,
   `tribe_bonus_cm = 0`).
7. Добавляет запись в `oracle_invocations` с `bonus_cm = base + tribe_bonus`
   (UNIQUE-индекс по `(player_id, moscow_date)` — last-line race-защита).
   Сохраняем **итоговую** прибавку: `oracle_invocations.bonus_cm` —
   это «что игрок выиграл сегодня», а не только базовый бросок.
   Раскладка по компонентам — в `audit_log` (двумя проводками с разными
   `source`).
8. Вызывает `ILengthGranter.grant(...)` дважды в той же транзакции:
   - **Базовый розыгрыш** — `source=ORACLE`, `delta=base_cm`,
     `idempotency_key="add_length:oracle:{player_id}:{date}:base"`,
     `reason="oracle_base"`.
   - **Бонус-за-племена** (только если `tribe_bonus_cm > 0`) —
     `source=ORACLE_TRIBE_BONUS`, `delta=tribe_bonus_cm`,
     `idempotency_key="add_length:oracle:{player_id}:{date}:tribe_bonus"`,
     `reason="oracle_tribe_bonus"`. Этот источник **НЕ** входит в
     `anticheat.organic_sources` и сидит в отдельном whitelist
     `anticheat.tribe_bonus_sources` — он не учитывается в
     anti-cheat-окне 24h/7d (ГДД §11.1).
   Сам `AddLength` проверяет anti-cheat soft-ban, клампит дельту
   по cap-ам, пишет audit `LENGTH_GRANT`, взводит trip-wire при
   превышении (Спринт 1.6.D — `add_length.py`).

Транзакция: всё внутри одного `IUnitOfWork` — «ритуал» (вставка в
`oracle_invocations`) и обе «прибавки длины» атомарны. `AddLength.grant`
работает в ambient-UoW режиме (Спринт 1.6.F): он не открывает свой
контекст, а только проверяет `uow.is_active` и зовёт репозитории
в сессии вызывающего.

Idempotency-стратегия:
- preflight (шаг 3) и БД-уникальность (шаг 7) защищают от race
  «два `/oracle` одновременно»;
- два `idempotency_key` в `AddLength.grant(...)` (`...:base` и
  `...:tribe_bonus`) отвечают за стабильную аналитику — дубликата
  `LENGTH_GRANT` с одним ключом не будет. Суффиксы намеренно разные:
  иначе вторая проводка была бы no-op-ом по идемпотентности.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pipirik_wars.application.dto.inputs import InvokeOracleInput
from pipirik_wars.application.oracle.templates import IOracleTemplateProvider
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.clan import IClanRepository
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
    - `result` — выпавший результат (`bonus_cm` = базовый бросок 1..20 см +
      выбранный `template`). Поле `result.bonus_cm` совпадает с `base_cm`
      ниже и **не** включает бонус-за-племена;
    - `base_cm` — базовый бросок (`uniform(bonus_min, bonus_max)`, ГДД §11);
    - `tribe_bonus_cm` — бонус-за-племена (Спринт 3.6-A, ГДД §11.1):
      `min(n_active_tribes * cm_per_tribe, cap_cm)`. Равен 0, если фичефлаг
      выключен или у игрока нет квалифицированных племён;
    - `n_active_tribes` — сколько активных племён засчитано (used handler-ом
      для строки «+N см за племена»). 0 при выключенном фичефлаге;
    - `total_cm` — итоговая прибавка длины за этот `/oracle` (= `base_cm` +
      `tribe_bonus_cm`); это ровно то значение, что записано в
      `oracle_invocations.bonus_cm` и применено к игроку (до клампа
      anti-cheat-ом, см. `player_after.length`);
    - `player_before` / `player_after` — снимки до/после; handler
      показывает игроку «было N см → стало M см»;
    - `moscow_date` — день, в который записан кулдаун (нужен handler-у
      на случай рендера «вернись завтра»).
    """

    result: OracleResult
    player_before: Player
    player_after: Player
    moscow_date: date
    base_cm: int
    tribe_bonus_cm: int
    n_active_tribes: int

    @property
    def total_cm(self) -> int:
        """Итоговая прибавка длины (= `base_cm` + `tribe_bonus_cm`)."""
        return self.base_cm + self.tribe_bonus_cm


class InvokeOracle:
    """Use-case «получить предсказание и +1..20 см длины»."""

    __slots__ = (
        "_balance",
        "_clans",
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
        clans: IClanRepository,
    ) -> None:
        self._uow = uow
        self._players = players
        self._history = history
        self._templates = templates
        self._balance = balance
        self._random = random
        self._length_granter = length_granter
        self._clock = clock
        self._clans = clans

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
            base_cm = result.bonus_cm

            # 1. Бонус-за-племена (Спринт 3.6-A, ГДД §11.1). При выключенном
            # фичефлаге репозиторий вообще не зовём — это разовый READ-only
            # запрос в той же транзакции, но даже его приятно не делать,
            # если фича выключена в проде.
            tribe_cfg = cfg.oracle.tribe_bonus
            if tribe_cfg.enabled:
                n_active_tribes = await self._clans.count_active_for_player(
                    player_id=player.id,
                    min_tribe_size=tribe_cfg.min_tribe_size,
                )
                tribe_bonus_cm = min(
                    n_active_tribes * tribe_cfg.cm_per_tribe,
                    tribe_cfg.cap_cm,
                )
            else:
                n_active_tribes = 0
                tribe_bonus_cm = 0
            total_cm = base_cm + tribe_bonus_cm

            now = self._clock.now()

            # 2. Сначала вставка в `oracle_invocations` — last-line race-защита
            # через UNIQUE-индекс; если здесь БД побила «два одновременных
            # /oracle» — выбрасываем бизнес-ошибку, UoW откатывается.
            # Сохраняем **итог** (base + tribe_bonus): `bonus_cm` в этой
            # таблице семантически — «сколько игрок получил сегодня»,
            # а не базовый бросок (раскладка хранится в audit-логе).
            try:
                await self._history.add(
                    OracleInvocation(
                        player_id=player.id,
                        moscow_date=moscow_date,
                        bonus_cm=total_cm,
                        template_id=result.template.id,
                        occurred_at=now,
                    )
                )
            except IntegrityError as exc:
                raise OracleAlreadyUsedTodayError(
                    player_id=player.id,
                    moscow_date=moscow_date,
                ) from exc

            # 3. Базовая прибавка длины — через единый ILengthGranter
            # (Спринт 1.6.F). `AddLength` в ambient-UoW режиме проверит
            # anti-cheat soft-ban, клампнет по cap-ам, запишет audit
            # `LENGTH_GRANT` (`source=ORACLE`) и trip-wire.
            base_idem_key = f"add_length:oracle:{player.id}:{moscow_date.isoformat()}:base"
            await self._length_granter.grant(
                player_id=player.id,
                delta_cm=base_cm,
                source=AuditSource.ORACLE,
                reason="oracle_base",
                idempotency_key=base_idem_key,
            )

            # 4. Бонус-за-племена — отдельная проводка `LENGTH_GRANT` с другим
            # `source` и idempotency-ключом (Спринт 3.6-A, ГДД §11.1).
            # Зовём только если бонус положителен — иначе `add_length(0)`
            # пишет лишний audit-no-op.
            if tribe_bonus_cm > 0:
                tribe_idem_key = (
                    f"add_length:oracle:{player.id}:{moscow_date.isoformat()}:tribe_bonus"
                )
                await self._length_granter.grant(
                    player_id=player.id,
                    delta_cm=tribe_bonus_cm,
                    source=AuditSource.ORACLE_TRIBE_BONUS,
                    reason="oracle_tribe_bonus",
                    idempotency_key=tribe_idem_key,
                )

            # 5. Перечитываем игрока, чтобы отдать handler-у финальный снапшот
            # (с учётом клампа или полной прибавки).
            saved = await self._players.get_by_id(player_id=player.id) or player

        return OracleInvoked(
            result=result,
            player_before=player,
            player_after=saved,
            moscow_date=moscow_date,
            base_cm=base_cm,
            tribe_bonus_cm=tribe_bonus_cm,
            n_active_tribes=n_active_tribes,
        )


__all__ = [
    "InvokeOracle",
    "OracleInvoked",
]
