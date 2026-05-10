"""Use-case `SpinPaidRoulette` (Спринт 4.1-A, ГДД §12.5).

Платная прокрутка рулетки за Telegram Stars (`SINGLE` за `1 ⭐` либо
`PACK_10` за `9 ⭐` ⇒ `pack10_spins` спинов одной транзакцией; ГДД §12.5.1).

Use-case — оркестратор всех побочных эффектов одной платной прокрутки:

1. **Idempotency-check** (`namespace="roulette_paid"`). Если ключ
   `(player_id, command.idempotency_key)` уже отмечен в idempotency-
   store — возвращаем `SpinPaidResult(outcomes=(), spent_stars=0,
   pack=command.pack, idempotent=True, payment=None)` без побочных
   эффектов. Bot-handler 4.1-A при таком исходе показывает
   «прокрутка уже завершена»-сообщение.
2. **Load Player**. Если игрока нет — `PlayerNotFoundError`.
3. **Thickness-гейт**: `player.thickness.level >=
   config.roulette.paid.min_thickness_level` (по дефолту `1` —
   доступ со старта, ГДД §12.5.1). Иначе —
   `RouletteThicknessGateError` без побочных эффектов.

   ⚠️ Длиновой гейт **отсутствует** — paid-рулетка стоит ⭐, а не см.

4. **Charge через `IPaymentLedger`**: `charge(player_id, STARS,
   cost_stars, idempotency_key, status=CONFIRMED, ...)`.
   `cost_stars` = `cost_stars_single` для `SINGLE`-pack-а либо
   `cost_stars_pack10` для `PACK_10`-а. Antifraud (4.1.4):
   ledger-port дедуплицирует по `idempotency_key`, конфликт суммы /
   игрока с тем же ключом → `IdempotencyConflictError`.

   На 4.1-A use-case вызывается **уже после** `successful_payment`-
   callback-а в bot-handler-е (Telegram-платёж подтверждён), поэтому
   платёж сразу пишется со статусом `CONFIRMED`. Pre-checkout flow
   (статус `PENDING`) обрабатывается отдельным handler-ом, который
   вообще не вызывает этот use-case.
5. **Audit `PAYMENT_RECORDED`** — одна запись с `target_kind=
   "payment"`, `target_id=<idempotency_key>`, `source=STARS_PAYMENT`.
6. **Pick исхода `n` раз** (`n=1` для `SINGLE`, `n=pack10_spins`
   для `PACK_10`) через чистый picker
   `domain.roulette.services.pick_paid_outcome(config, random,
   crypto_pool_empty=True)`. На 4.1-A крипто-пул всегда пуст
   (крипто-инфраструктура — Спринты 4.1-D / 4.1-E). Picker возвращает
   `RouletteOutcome(kind, length_cm)`.

   Каждый спин — **независимый ролл** picker-а (как и при `n=1`),
   статистические гарантии E[CM | spin, paid] ≈ 26.7 см распространяются
   на отдельные роллы, но не на сумму (т. е. дисперсия 10-pack-а в
   `√10` раз меньше per-spin).
7. **Запись `n` строк в event-log `roulette_spins`** через
   `IRouletteSpinRepository.record(spin=...)`. Каждый спин получает
   свой собственный `idempotency_key` вида
   `f"{command.idempotency_key}:{i}"` (где `i` — индекс 0..n-1) —
   DB-уровневая UNIQUE-дедупликация защищает от частичной повторной
   записи (если transaction отмёрла после k-го спина).

   ⚠️ На 4.1-A `RouletteSpin`-сущность не несёт `variant`-поля
   (`free` vs `paid`); оно появится в Спринте 4.1-B миграцией с
   дефолтом `'free'` для исторических записей. На 4.1-A paid-спины
   неотличимы от free-спинов в `roulette_spins`-таблице иначе как по
   суффиксу `idempotency_key` (вход `paid_roulette:...`) и по
   audit-логу (`PAYMENT_RECORDED` идёт в одной транзакции).
8. **Audit `ROULETTE_SPIN`** — одна запись на каждый из `n` спинов
   с `target_kind="roulette_spin"`, `target_id=<spin-key>`,
   `after={kind, length_cm?}`, `reason="paid_roulette_spin"`.
9. **LENGTH-исходы → reward**: для каждого LENGTH-исхода вызывается
   `ILengthGranter.grant(player_id, delta=outcome.length_cm,
   source=ROULETTE_PAID_REWARD, idempotency_key=
   "add_length:roulette_paid_reward:{player_id}:{spin-key}")`.
   Идемпотентность reward-grant-а — собственная (внутри
   `AddLength.grant`).
10. **Mark idempotency** (`<namespace>:<root>`). До этой строки любое
    исключение откатит UoW (включая charge и spin-records),
    idempotency-mark не запишется, retry начнёт всё сначала.

Не-LENGTH исходы (`item` / `scroll_regular` / `scroll_blessed` /
`crypto_lot`) на 4.1-A пишутся только в audit-payload и в
`roulette_spins`. Конкретные эффекты (выкатить предмет / скролл /
крипто-лот) реализуются в Спринтах 4.1-C → 4.1-E (там use-case
дополнится pre-resolve-шагом аналогично free-варианту).

Транзакционность: всё внутри `async with self._uow`. Любое исключение
от любого шага откатит UoW (в том числе charge, audit-записи и
запись spin-ов), сохранив консистентность таблиц `users` ↔ `payments`
↔ `roulette_spins` ↔ `audit_log` ↔ `idempotency_keys`.

Антифрод (4.1.4):
* idempotency-двойная защита: `IIdempotencyKey` (use-case-уровень) +
  `IPaymentLedger` (ledger-уровень, `UNIQUE (player_id,
  idempotency_key)`-индекс таблицы `payments`).
* `IdempotencyConflictError` (см. `domain/monetization/errors.py`)
  поднимается если bot-handler 4.1-A пытается зарегистрировать новый
  платёж под уже существующим ключом, но с другой суммой / игроком.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.monetization.entities import Payment, PaymentStatus
from pipirik_wars.domain.monetization.ports import IPaymentLedger
from pipirik_wars.domain.monetization.value_objects import Currency, IdempotencyKey
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.roulette import (
    IRouletteSpinRepository,
    RouletteOutcome,
    RouletteOutcomeKind,
    RouletteSpin,
    pick_paid_outcome,
)
from pipirik_wars.domain.roulette.errors import RouletteThicknessGateError
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

__all__ = [
    "PaidRoulettePack",
    "SpinPaidRoulette",
    "SpinPaidRouletteCommand",
    "SpinPaidRouletteResult",
]

_NAMESPACE = "roulette_paid"
_REASON_SPIN = "paid_roulette_spin"
_REASON_PAYMENT = "paid_roulette_charge"


class PaidRoulettePack(StrEnum):
    """Тип покупки платной рулетки (ГДД §12.5.1, Спринт 4.1-A).

    `SINGLE` — одиночная прокрутка за `cost_stars_single` ⭐
    (по дефолту `1 ⭐`). Один спин в одной транзакции.

    `PACK_10` — 10-pack за `cost_stars_pack10` ⭐ (по дефолту `9 ⭐`,
    скидка ~10 % vs `10 × cost_stars_single`). `pack10_spins` спинов
    одной транзакцией (по дефолту `10`).

    Стабильные машинные id, попадают в `audit_log.payload.pack` и в
    `payments.payload.pack`. Не менять без миграции.
    """

    SINGLE = "single"
    PACK_10 = "pack_10"


@dataclass(frozen=True, slots=True)
class SpinPaidRouletteCommand:
    """Команда use-case `SpinPaidRoulette`.

    Поля:
    - `player_id` — id игрока (FK → `users.id`).
    - `pack` — тип покупки (`SINGLE` либо `PACK_10`, ГДД §12.5.1).
    - `idempotency_key` — идемпотентный ключ платежа (валидирован VO
      `IdempotencyKey`). Bot-handler 4.1-A генерирует ключ как
      `IdempotencyKey(f"paid_roulette:{player_id}:{tg_payment_charge_id}")`
      где `tg_payment_charge_id` — стабильный id платежа от Telegram.
      Тот же ключ попадает в `payments.idempotency_key` (DB-уровневая
      UNIQUE-дедупликация). Use-case формирует root-key namespace-а
      `roulette_paid` поверх ключа платежа: `f"{namespace}:{player_id}|{key}"`.
    - `provider_payment_id` — `successful_payment.telegram_payment_charge_id`
      от Telegram (опционально; на тестах / когда не нужен — `None`).
      Сохраняется в `payments.provider_payment_id`.
    - `tg_user_id` — `actor_id` для audit-записей (TG user-id, не
      внутренний `player_id`). На 4.1-A совпадает с `tg_id` игрока.
    """

    player_id: int
    pack: PaidRoulettePack
    idempotency_key: IdempotencyKey
    provider_payment_id: str | None = None


@dataclass(frozen=True, slots=True)
class SpinPaidRouletteResult:
    """Результат use-case `SpinPaidRoulette`.

    - `outcomes` — `tuple[RouletteOutcome, ...]` длины `1` (для `SINGLE`)
      или `pack10_spins` (для `PACK_10`). Пустой `tuple` при
      `idempotent=True`: use-case не знает оригинальных outcome-ов без
      чтения из БД (порт `IRouletteSpinRepository` пока не имеет
      `get_by_idempotency_key`-prefix-метода; добавим в 4.1-B).
    - `spent_stars` — фактически списанные ⭐. На первом успешном вызове
      — `cost_stars_single` либо `cost_stars_pack10` из конфига; при
      `idempotent=True` — `0`.
    - `pack` — тип покупки (отражение `command.pack`).
    - `payment` — `Payment` от `IPaymentLedger.charge(...)` (либо
      свежевставленный, либо существующий при honest retry). `None`
      при `idempotent=True`.
    - `idempotent` — `True`, если use-case не выполнял побочные
      эффекты, потому что `idempotency_key` уже был в idempotency-store.
    """

    outcomes: tuple[RouletteOutcome, ...]
    spent_stars: int
    pack: PaidRoulettePack
    payment: Payment | None
    idempotent: bool


class SpinPaidRoulette:
    """Use-case «прокрутить платную рулетку за Telegram Stars» (ГДД §12.5)."""

    __slots__ = (
        "_audit",
        "_balance",
        "_clock",
        "_idempotency",
        "_length_granter",
        "_payments",
        "_players",
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
        payments: IPaymentLedger,
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
        self._payments = payments
        self._length_granter = length_granter
        self._balance = balance
        self._audit = audit
        self._idempotency = idempotency
        self._random = random
        self._clock = clock

    async def execute(self, command: SpinPaidRouletteCommand) -> SpinPaidRouletteResult:
        """Прокрутить платную рулетку. Полное описание контракта — в docstring модуля."""
        async with self._uow:
            root_key = self._idempotency.build(
                _NAMESPACE,
                [str(command.player_id), command.idempotency_key.value],
            )
            if await self._idempotency.is_seen(root_key):
                return SpinPaidRouletteResult(
                    outcomes=(),
                    spent_stars=0,
                    pack=command.pack,
                    payment=None,
                    idempotent=True,
                )

            player = await self._players.get_by_id(player_id=command.player_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=command.player_id)

            paid_cfg = self._balance.get().roulette.paid
            if paid_cfg is None:
                # Defence-in-depth: bot-handler 4.1-A не должен пускать в use-case
                # без `roulette.paid`-блока в `balance.yaml` (UI просто не покажет
                # /roulette_paid). Если всё-таки пришло — это баг в DI / config-loader.
                raise RuntimeError(
                    "config.roulette.paid is None (paid roulette config missing); "
                    "bot-handler must not invoke SpinPaidRoulette without paid-config",
                )
            if player.thickness.level < paid_cfg.min_thickness_level:
                raise RouletteThicknessGateError(
                    player_id=command.player_id,
                    thickness_level=player.thickness.level,
                    required_level=paid_cfg.min_thickness_level,
                )

            now = self._clock.now()
            assert player.id is not None

            # Step 4 — определить cost / spins.
            if command.pack is PaidRoulettePack.SINGLE:
                cost_stars = paid_cfg.cost_stars_single
                n_spins = 1
            else:
                cost_stars = paid_cfg.cost_stars_pack10
                n_spins = paid_cfg.pack10_spins

            # Step 4 — charge через ledger (idempotent).
            payment = await self._payments.charge(
                player_id=player.id,
                currency=Currency.STARS,
                amount_native=cost_stars,
                idempotency_key=command.idempotency_key,
                status=PaymentStatus.CONFIRMED,
                occurred_at=now,
                provider_payment_id=command.provider_payment_id,
                payload=MappingProxyType(
                    {
                        "pack": command.pack.value,
                        "n_spins": str(n_spins),
                    }
                ),
            )

            # Step 5 — audit `PAYMENT_RECORDED` (одна запись на платёж).
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PAYMENT_RECORDED,
                    actor_id=player.tg_id,
                    target_kind="payment",
                    target_id=command.idempotency_key.value,
                    before=None,
                    after={
                        "currency": Currency.STARS.value,
                        "amount_native": cost_stars,
                        "status": payment.status.value,
                        "pack": command.pack.value,
                        "n_spins": n_spins,
                    },
                    reason=_REASON_PAYMENT,
                    idempotency_key=f"{root_key}:payment",
                    occurred_at=now,
                    source=AuditSource.STARS_PAYMENT,
                )
            )

            # Step 6–9 — `n_spins` независимых роллов picker-а с записью
            # в event-log, audit и (для LENGTH-исхода) грантом награды.
            outcomes_list: list[RouletteOutcome] = []
            for i in range(n_spins):
                outcome = pick_paid_outcome(
                    config=paid_cfg,
                    random=self._random,
                    crypto_pool_empty=True,
                )
                outcomes_list.append(outcome)

                spin_idem = f"{command.idempotency_key.value}:{i}"
                spin = RouletteSpin(
                    player_id=player.id,
                    occurred_at=now,
                    outcome=outcome,
                    idempotency_key=spin_idem,
                )
                await self._roulette_spins.record(spin=spin)

                spin_after: dict[str, object] = {"kind": outcome.kind.value}
                if outcome.length_cm is not None:
                    spin_after["length_cm"] = outcome.length_cm
                await self._audit.record(
                    AuditEntry(
                        action=AuditAction.ROULETTE_SPIN,
                        actor_id=player.tg_id,
                        target_kind="roulette_spin",
                        target_id=spin_idem,
                        before=None,
                        after=spin_after,
                        reason=_REASON_SPIN,
                        idempotency_key=f"{root_key}:spin:{i}",
                        occurred_at=now,
                    )
                )

                if outcome.kind is RouletteOutcomeKind.LENGTH:
                    assert outcome.length_cm is not None
                    await self._length_granter.grant(
                        player_id=player.id,
                        delta_cm=outcome.length_cm,
                        source=AuditSource.ROULETTE_PAID_REWARD,
                        reason="roulette_paid_reward",
                        idempotency_key=(
                            f"add_length:roulette_paid_reward:{player.id}:{spin_idem}"
                        ),
                    )

            # Step 10 — mark idempotency (атомарно с UoW).
            await self._idempotency.mark(root_key, namespace=_NAMESPACE)

        return SpinPaidRouletteResult(
            outcomes=tuple(outcomes_list),
            spent_stars=cost_stars,
            pack=command.pack,
            payment=payment,
            idempotent=False,
        )
