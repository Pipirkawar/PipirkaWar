"""Use-case `RecordDonation` (Спринт 4.1-B, ГДД §12.6).

Зачисление 10%-доли подтверждённого платежа в призовой пул (`prize_pool`)
+ запись audit-события `PRIZE_POOL_INCREMENT`.

ГДД §12.6.1: «10% от каждого донат-зачисления (Stars / TON-нано / USDT-decimal)
автоматически идёт в призовой пул соответствующей валюты». Use-case вызывается
из flow `SpinPaidRoulette` (4.1-B / Шаг B.5) **сразу после** успешного
`IPaymentLedger.charge(...)` подтверждённого платежа — внутри той же
транзакции UoW, чтобы пул-инкремент, audit-запись и платёж были
атомарны (без «потерянного доната» / «потерянного аудита»).

Вычисление дельты — `floor`-округление: `donation_amount_native =
payment_amount_native // _DONATION_DIVISOR`. ГДД-§12.6.1 не указывает
правило округления при `amount % 10 != 0`; решено стартовать с `floor`-варианта
(в пользу платформы — пользователь не теряет ничего, потому что платит
ровно столько, сколько списано в Telegram). При фидбеке на review этот
делитель / правило округления могут поменяться (см. `current_tasks.md`,
секция «Известные блокеры»).

`donation == 0` (платежи `<10` native-юнитов) — фильтруется на уровне
use-case: `apply_increment` не вызывается, audit **не** пишется,
в результате стоит `applied=False`, а `pool_after` берётся через
`IPrizePoolRepository.get_current()`. Это эквивалент no-op-инкремента
и сохраняет инвариант «нет нулевых-дельт в audit-логе».

Audit-запись на `applied=True` (B.4):

* `action=AuditAction.PRIZE_POOL_INCREMENT`, `source=AuditSource.PRIZE_POOL_INCREMENT`.
* `actor_id=None` — донат-инкремент пула — системное событие,
  привязка к игроку идёт через `target_id` (`<idempotency_key>:donation`),
  где `idempotency_key` несёт `paid_roulette:<player_id>:<charge_id>`-формат.
* `target_kind="prize_pool"`, `target_id=f"{idempotency_key}:donation"` —
  стабильный ключ для дедупликации в админ-просмотре audit-лога.
* `before=None`, `after={"currency": ..., "amount_native": <delta>,
  "pool_after_native": <пул в этой валюте после инкремента>}`. Парного
  `before`-снапшота не пишем (delta + after однозначно восстанавливают
  before).
* `idempotency_key=f"{cmd.idempotency_key}:prize_pool"` — отдельный
  scope от `:payment` (см. `SpinPaidRoulette`), чтобы один и тот же
  root-key давал стабильно разные audit-`idempotency_key`-маркеры
  на каждое event.
* `delta_cm=None` — пул-инкремент не length-source.

Идемпотентность use-case-а — наследуется от upstream-вызова: caller
(`SpinPaidRoulette` в B.5) сам идемпотентен по `IdempotencyKey` через
`IPaymentLedger.charge` + `IIdempotencyKey.mark`. Внутри UoW
`RecordDonation.execute` срабатывает только когда платёж был реально
вставлен (а не возвращён как existing-row при honest retry). Поэтому
дедупликация на стороне `RecordDonation` не нужна — ровно один донат
на ровно один платёж по конструкции.

Транзакционность: use-case **не открывает** UoW сам — caller отвечает
за `async with self._uow`. Это позволяет прокинуть `RecordDonation`
в `SpinPaidRoulette` без вложенных транзакций и без двойного UoW-ресурса.
Любая ошибка из репозитория или audit-логгера откатывает caller-овую
UoW (in line с конвенцией `IAuditLogger`).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.monetization.entities import PrizePool
from pipirik_wars.domain.monetization.ports import IPrizePoolRepository
from pipirik_wars.domain.monetization.value_objects import Currency, IdempotencyKey
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    AuditSource,
    IAuditLogger,
    IClock,
)

__all__ = [
    "RecordDonation",
    "RecordDonationCommand",
    "RecordDonationResult",
]

# Доля платежа, направляемая в призовой пул (ГДД §12.6.1).
# Делим native-amount на `_DONATION_DIVISOR` (целочисленно) — `floor`-округление
# в пользу платформы. При смене этой константы обнови
# `docs/game_design.md` §12.6.1.
_DONATION_DIVISOR = 10

# Стабильный `reason`-маркер audit-записи донат-инкремента пула.
# Пишется в `AuditEntry.reason`; admin-handler-ы 4.1-E фильтруют
# по этой строке для отчёта `/prize_pool history`.
_REASON_PRIZE_POOL_INCREMENT = "prize_pool_increment"


@dataclass(frozen=True, slots=True)
class RecordDonationCommand:
    """Команда use-case `RecordDonation`.

    Поля:
    - `currency` — валюта донат-зачисления (`STARS` / `TON_NANO` / `USDT_DECIMAL`).
      Должна совпадать с валютой исходного платежа (`Payment.currency`).
    - `payment_amount_native` — сумма исходного платежа в native-юнитах
      валюты (`>= 0`). Эквивалентен `Payment.amount_native`. От неё
      вычисляется `donation = payment_amount_native // 10` (`floor`-округление,
      ГДД §12.6.1).
    - `idempotency_key` — `IdempotencyKey` исходного платежа. Прокидывается
      из caller-а ради аудит-записи (B.4) — таргет-id audit-записи
      пула образуется как `f"{idempotency_key.value}:donation"`.

    `RecordDonation.execute(...)` вызывается caller-ом внутри его
    собственного `async with uow:`-блока. Use-case полагается на
    транзакционную атомарность caller-а.
    """

    currency: Currency
    payment_amount_native: int
    idempotency_key: IdempotencyKey


@dataclass(frozen=True, slots=True)
class RecordDonationResult:
    """Результат use-case `RecordDonation`.

    Поля:
    - `donation_amount_native` — фактически зачисленная в пул дельта в
      native-юнитах валюты команды (`>= 0`). Равна
      `payment_amount_native // _DONATION_DIVISOR`. При
      `payment_amount_native < _DONATION_DIVISOR` — `0`.
    - `pool_after` — снапшот всего пула (по всем валютам) после
      применения донат-инкремента. Берётся либо как результат
      `IPrizePoolRepository.apply_increment(...)`, либо (для `donation == 0`)
      через `IPrizePoolRepository.get_current()`.
    - `applied` — `True`, если дельта была вычислена положительной
      и применилась через `apply_increment`; `False` — если
      `donation == 0` (платёж был `< _DONATION_DIVISOR` native-юнитов)
      и `apply_increment` не вызывался.
    """

    donation_amount_native: int
    pool_after: PrizePool
    applied: bool


class RecordDonation:
    """Use-case: 10% подтверждённого платежа → призовой пул + audit.

    Архитектура (ГДД §0): чистый application-слой, без UoW (caller
    оборачивает в `async with self._uow`), без побочных Telegram-вызовов.
    Только репозиторий пула, audit-логгер, часы и чистая арифметика.
    """

    __slots__ = ("_audit", "_clock", "_pool_repo")

    def __init__(
        self,
        *,
        prize_pool_repository: IPrizePoolRepository,
        audit_logger: IAuditLogger,
        clock: IClock,
    ) -> None:
        """DI-конструктор.

        Args:
            prize_pool_repository: порт репозитория призового пула
                (`IPrizePoolRepository`). В B.3 реализован
                `SqlAlchemyPrizePoolRepository`; в unit-тестах —
                `FakePrizePoolRepository`.
            audit_logger: порт audit-логгера (`IAuditLogger`). Запись
                идёт в той же UoW, что и `apply_increment(...)`. В
                unit-тестах — `FakeAuditLogger`.
            clock: часы (`IClock`). Источник `occurred_at` для audit-
                записи. В unit-тестах — `FakeClock`.
        """
        self._pool_repo = prize_pool_repository
        self._audit = audit_logger
        self._clock = clock

    async def execute(self, command: RecordDonationCommand) -> RecordDonationResult:
        """Выполнить расчёт + инкремент пула + audit-запись.

        Шаги:

        1. Вычислить `donation = command.payment_amount_native // 10`
           (`floor`-округление, ГДД §12.6.1).
        2. Если `donation <= 0` — пропустить инкремент и audit, вернуть
           текущий снапшот пула с `applied=False`.
        3. Иначе — `await self._pool_repo.apply_increment(currency, donation)`;
           записать `AuditEntry(action=PRIZE_POOL_INCREMENT, source=...)`
           с payload `currency` / `amount_native` / `pool_after_native`;
           вернуть свежий снапшот пула с `applied=True`.

        Контракт: вызывающий код отвечает за UoW-транзакцию. Любая
        ошибка из репозитория или audit-логгера пробрасывается без
        catch-ов — это инвариант «потерянного аудита нет».
        """
        donation_amount_native = command.payment_amount_native // _DONATION_DIVISOR
        if donation_amount_native <= 0:
            current_pool = await self._pool_repo.get_current()
            return RecordDonationResult(
                donation_amount_native=0,
                pool_after=current_pool,
                applied=False,
            )

        pool_after = await self._pool_repo.apply_increment(
            currency=command.currency,
            amount_native=donation_amount_native,
        )

        await self._audit.record(
            AuditEntry(
                action=AuditAction.PRIZE_POOL_INCREMENT,
                actor_id=None,
                target_kind="prize_pool",
                target_id=f"{command.idempotency_key.value}:donation",
                before=None,
                after={
                    "currency": command.currency.value,
                    "amount_native": donation_amount_native,
                    "pool_after_native": pool_after.balance_for(command.currency),
                },
                reason=_REASON_PRIZE_POOL_INCREMENT,
                idempotency_key=f"{command.idempotency_key.value}:prize_pool",
                occurred_at=self._clock.now(),
                source=AuditSource.PRIZE_POOL_INCREMENT,
            )
        )

        return RecordDonationResult(
            donation_amount_native=donation_amount_native,
            pool_after=pool_after,
            applied=True,
        )
