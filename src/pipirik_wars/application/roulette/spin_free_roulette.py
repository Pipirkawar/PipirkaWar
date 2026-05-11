"""Use-case `SpinFreeRoulette` (Спринт 3.5-C, ГДД §12.4).

Одна прокрутка free-to-play рулетки. Use-case — оркестратор всех
побочных эффектов одной прокрутки:

1. **Idempotency-check** (`namespace="roulette_free"`). Если ключ
   `(player_id, command.idempotency_key)` уже отмечен в idempotency-
   store — возвращаем `SpinResult(outcome=None, spent_cm=0,
   idempotent=True)` без каких-либо побочных эффектов. Bot-handler
   3.5-D при таком исходе либо показывает «прокрутка уже завершена»,
   либо (после расширения порта `IRouletteSpinRepository` в 3.5-D
   методом `get_by_idempotency_key`) восстанавливает оригинальный
   outcome из БД.
2. **Load Player**. Если игрока нет — `PlayerNotFoundError`.
3. **Thickness-гейт**: `player.thickness.level >= config.roulette.free.
   min_thickness_level` (по дефолту `2`, ГДД §12.4.2). Иначе —
   `RouletteThicknessGateError` без побочных эффектов.
4. **Длиновой гейт**: `player.length.cm >= config.roulette.free.cost_cm`
   (по дефолту `100`). Иначе — `InsufficientLengthForRouletteError`.
5. **Списание стоимости** (-`cost_cm` см). Применяется напрямую через
   `Player.with_length(...)`, минуя `ILengthGranter` (тот по контракту
   принимает только положительные дельты не-`admin_refund`-источников).
   Сопровождается audit-записью `LENGTH_GRANT` с `source=
   ROULETTE_FREE_COST` и `delta_cm=-cost_cm` (источник **не** в
   `anticheat.organic_sources` — рулетка не учитывается в anti-cheat
   24h/7d-окнах). Файл use-case-а зарегистрирован в `_ALLOWED_FILES`
   guard-теста `tests/unit/architecture/test_length_grant_guard.py` —
   аналогично `dungeon/finish_run.py` для loss-исходов.
6. **Pick исхода** через чистый picker
   `domain.roulette.services.pick_roulette_outcome(config, random,
   active_lots=...)`. **С Шага C.6.b** use-case вызывает
   `IPrizeLotRepository.list_active(currency=Currency.STARS)` перед
   picker-ом и передаёт результат в `active_lots`. Пустой список
   равносилен «крипто-пул пуст» — picker перевыронит `CRYPTO_LOT`
   в `LENGTH`. Непустой — picker может вернуть
   `RouletteOutcome.crypto_lot(lot_id=...)`. **Открытый вопрос C.6.b:**
   валюта лота для free-рулетки — MVP-выбор `STARS` (тот же что в
   paid; ГДД §12.4.2 — уточнить). Резервирование
   (`update_status(lot_id, RESERVED)` + audit `PRIZE_LOT_RESERVED`)
   придёт в C.6.c туда же после picker-а.
   Picker возвращает `RouletteOutcome(kind, length_cm?, lot_id?)`.
7. **Запись в event-log** `roulette_spins` через
   `IRouletteSpinRepository.record(spin=...)` (append-only,
   идемпотентность по `idempotency_key` на уровне БД).
8. **Audit `ROULETTE_SPIN`** с `target_kind="roulette_spin"`,
   `target_id=command.idempotency_key`, `after={kind, length_cm?}`.
9. **LENGTH-исход → reward**: `ILengthGranter.grant(player_id, delta=
   outcome.length_cm, source=ROULETTE_FREE_REWARD, idempotency_key=
   "<root>:reward")`. Идемпотентность reward-grant-а — собственная
   (внутри `AddLength.grant`, см. Спринт 1.6.D).
10. **Mark idempotency** (`<namespace>:<root>`). Если до этой строки
    случилось исключение — UoW откатит транзакцию, idempotency-mark
    не запишется, retry начнёт всё сначала (включая spin-record —
    он использует `command.idempotency_key` как DB-уровневый
    UNIQUE-ключ, так что повторная вставка той же строки безопасна).

Не-LENGTH исходы (`item` / `scroll_regular` / `scroll_blessed` /
`crypto_lot`) на 3.5-C записываются только в audit-payload и в
`roulette_spins`. Конкретные эффекты (выкатить предмет / скролл /
крипто-лот) реализуются в Спринтах 3.5-D и Phase 4 — там use-case
дополнится pre-resolve-шагом.

Транзакционность: всё внутри `async with self._uow`. Любое исключение
от любого шага откатит UoW (в том числе списание стоимости и audit-
запись), сохранив консистентность таблиц `users` ↔ `roulette_spins`
↔ `audit_log` ↔ `idempotency_keys`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.monetization.entities import PrizeLotStatus
from pipirik_wars.domain.monetization.errors import PrizeLotStatusTransitionError
from pipirik_wars.domain.monetization.ports import IPrizeLotRepository
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.domain.player import IPlayerRepository, Length
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.roulette import (
    IRouletteSpinRepository,
    RouletteOutcome,
    RouletteOutcomeKind,
    RouletteSpin,
    pick_length_only_outcome,
    pick_roulette_outcome,
)
from pipirik_wars.domain.roulette.errors import (
    InsufficientLengthForRouletteError,
    RouletteThicknessGateError,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IIdempotencyKey,
    IRandom,
    IUnitOfWork,
)
from pipirik_wars.domain.shared.ports.audit import AuditSource

_NAMESPACE = "roulette_free"


@dataclass(frozen=True, slots=True)
class SpinFreeRouletteCommand:
    """Команда use-case `SpinFreeRoulette`.

    Поля:
    - `player_id` — id игрока (FK → `users.id`).
    - `idempotency_key` — короткий стабильный суффикс, по которому
      use-case строит полный idempotency-key (`f"{namespace}:{player_id}|{key}"`).
      Bot-handler 3.5-D обычно передаёт что-то вроде `f"msg:{tg_message_id}"`.
      Тот же суффикс попадает в `RouletteSpin.idempotency_key`
      (DB-уровневая UNIQUE-дедупликация).
    """

    player_id: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class SpinResult:
    """Результат use-case `SpinFreeRoulette`.

    - `outcome` — разыгранный `RouletteOutcome` (`kind` + опциональный
      `length_cm`). `None` при `idempotent=True` (повторный вызов с
      тем же `idempotency_key` после успешного предыдущего): use-case
      не знает оригинального outcome без чтения из БД, и порт
      `IRouletteSpinRepository` пока не имеет `get_by_idempotency_key`
      (расширим в 3.5-D, когда bot-UI понадобится восстановление
      исхода для retry-сообщения). До тех пор bot-handler 3.5-D при
      `idempotent=True` показывает короткое «прокрутка уже завершена»-сообщение.
    - `spent_cm` — фактически списанные см. На первом успешном вызове —
      `cost_cm` из конфига (`100` см по дефолту). При `idempotent=True` — `0`.
    - `idempotent` — `True`, если use-case не выполнял побочные эффекты,
      потому что `idempotency_key` уже был в idempotency-store.
    """

    outcome: RouletteOutcome | None
    spent_cm: int
    idempotent: bool


class SpinFreeRoulette:
    """Use-case «прокрутить free-рулетку» (ГДД §12.4)."""

    __slots__ = (
        "_audit",
        "_balance",
        "_clock",
        "_idempotency",
        "_length_granter",
        "_players",
        "_prize_lots",
        "_random",
        "_roulette_spins",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        roulette_spins: IRouletteSpinRepository,
        prize_lots: IPrizeLotRepository,
        length_granter: ILengthGranter,
        balance: IBalanceConfig,
        audit: IAuditLogger,
        idempotency: IIdempotencyKey,
        random: IRandom,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._roulette_spins = roulette_spins
        self._prize_lots = prize_lots
        self._length_granter = length_granter
        self._balance = balance
        self._audit = audit
        self._idempotency = idempotency
        self._random = random
        self._clock = clock

    async def execute(self, command: SpinFreeRouletteCommand) -> SpinResult:
        """Прокрутить free-рулетку. Полное описание контракта — в docstring модуля."""
        async with self._uow:
            root_key = self._idempotency.build(
                _NAMESPACE,
                [str(command.player_id), command.idempotency_key],
            )
            if await self._idempotency.is_seen(root_key):
                return SpinResult(outcome=None, spent_cm=0, idempotent=True)

            player = await self._players.get_by_id(player_id=command.player_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=command.player_id)

            roulette_cfg = self._balance.get().roulette.free
            if player.thickness.level < roulette_cfg.min_thickness_level:
                raise RouletteThicknessGateError(
                    player_id=command.player_id,
                    thickness_level=player.thickness.level,
                    required_level=roulette_cfg.min_thickness_level,
                )
            if player.length.cm < roulette_cfg.cost_cm:
                raise InsufficientLengthForRouletteError(
                    player_id=command.player_id,
                    length_cm=player.length.cm,
                    cost_cm=roulette_cfg.cost_cm,
                )

            now = self._clock.now()
            assert player.id is not None

            # Step 5: списание стоимости (прямой `with_length` минуя
            # `ILengthGranter`, аналогично loss-исходу в `dungeon/finish_run.py`).
            after_cost_player = player.with_length(
                Length(cm=player.length.cm - roulette_cfg.cost_cm),
                now=now,
            )
            saved_after_cost = await self._players.save(after_cost_player)
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.LENGTH_GRANT,
                    actor_id=player.tg_id,
                    target_kind="player",
                    target_id=str(player.id),
                    before={"length_cm": player.length.cm},
                    after={"length_cm": saved_after_cost.length.cm},
                    reason="roulette_free_cost",
                    idempotency_key=f"{root_key}:cost",
                    occurred_at=now,
                    source=AuditSource.ROULETTE_FREE_COST,
                    delta_cm=-roulette_cfg.cost_cm,
                )
            )

            # Step 6: pick outcome.
            # Шаг C.6.b: реальный запрос активных лотов из репозитория.
            # MVP-валюта free-рулетки — `Currency.STARS` (открытый вопрос
            # C.6.b: ГДД §12.4.2/§12.5.2 — уточнить, какую валюту даёт
            # free CRYPTO_LOT). Пустой результат — picker перевыронит
            # `CRYPTO_LOT → LENGTH` (совпадение с C.5-поведением).
            active_lots = await self._prize_lots.list_active(currency=Currency.STARS)
            outcome = pick_roulette_outcome(
                config=roulette_cfg,
                random=self._random,
                active_lots=active_lots,
            )

            # Шаг C.6.c/d: резервирование лота при CRYPTO_LOT-исходе.
            # `update_status(lot_id, RESERVED)` в той же UoW что и спин +
            # audit запись `PRIZE_LOT_RESERVED` с shape по C.6.a.
            # C.6.d race-fallback: если `update_status` бросает
            # `PrizeLotStatusTransitionError` (другой игрок забронировал
            # этот же лот между `list_active` и `update_status`),
            # подменяем outcome на LengthGain (без retry-loop — детерминистично).
            if outcome.kind is RouletteOutcomeKind.CRYPTO_LOT:
                assert outcome.lot_id is not None
                try:
                    reserved_lot = await self._prize_lots.update_status(
                        lot_id=outcome.lot_id,
                        new_status=PrizeLotStatus.RESERVED,
                    )
                except PrizeLotStatusTransitionError:
                    # C.6.d: лот уже забронирован — подменяем выигрыш на LengthGain.
                    outcome = pick_length_only_outcome(
                        length_buckets=roulette_cfg.length_buckets,
                        random=self._random,
                    )
                else:
                    await self._audit.record(
                        AuditEntry(
                            action=AuditAction.PRIZE_LOT_RESERVED,
                            actor_id=player.tg_id,
                            target_kind="prize_lot",
                            target_id=f"{reserved_lot.id}:reserved",
                            before=None,
                            after={
                                "lot_id": reserved_lot.id,
                                "currency": reserved_lot.currency.value,
                                "amount_native": reserved_lot.amount_native,
                                "prev_status": PrizeLotStatus.ACTIVE.value,
                                "reserved_at": now.isoformat(),
                                "player_id": player.id,
                                "spin_kind": "free",
                            },
                            reason="free_roulette_reserve_lot",
                            idempotency_key=f"{root_key}:reserve:{reserved_lot.id}",
                            occurred_at=now,
                            source=AuditSource.PRIZE_LOT_RESERVED,
                        )
                    )

            # Step 7: запись в event-log `roulette_spins`.
            spin = RouletteSpin(
                player_id=player.id,
                occurred_at=now,
                outcome=outcome,
                idempotency_key=command.idempotency_key,
            )
            await self._roulette_spins.record(spin=spin)

            # Step 8: audit `ROULETTE_SPIN`.
            spin_after: dict[str, object] = {"kind": outcome.kind.value}
            if outcome.length_cm is not None:
                spin_after["length_cm"] = outcome.length_cm
            if outcome.lot_id is not None:
                spin_after["lot_id"] = outcome.lot_id
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.ROULETTE_SPIN,
                    actor_id=player.tg_id,
                    target_kind="roulette_spin",
                    target_id=command.idempotency_key,
                    before=None,
                    after=spin_after,
                    reason="free_roulette_spin",
                    idempotency_key=root_key,
                    occurred_at=now,
                )
            )

            # Step 9: LENGTH-исход → reward через `ILengthGranter`.
            # Префикс `add_length:` обязателен — внутри `AddLength.grant`
            # `IIdempotencyKey.mark` валидирует, что ключ начинается с
            # namespace `add_length` (см. `dungeon/finish_run.py:114`).
            if outcome.kind is RouletteOutcomeKind.LENGTH:
                assert outcome.length_cm is not None
                await self._length_granter.grant(
                    player_id=player.id,
                    delta_cm=outcome.length_cm,
                    source=AuditSource.ROULETTE_FREE_REWARD,
                    reason="roulette_free_reward",
                    idempotency_key=(
                        f"add_length:roulette_free_reward:{player.id}:{command.idempotency_key}"
                    ),
                )

            # Step 10: mark idempotency (атомарно с UoW).
            await self._idempotency.mark(root_key, namespace=_NAMESPACE)

        return SpinResult(
            outcome=outcome,
            spent_cm=roulette_cfg.cost_cm,
            idempotent=False,
        )
