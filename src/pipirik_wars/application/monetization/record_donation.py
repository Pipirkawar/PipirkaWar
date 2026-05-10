"""Use-case `RecordDonation` (Спринт 4.1-B, ГДД §12.6).

Зачисление 10%-доли подтверждённого платежа в призовой пул (`prize_pool`).

ГДД §12.6.1: «10% от каждого донат-зачисления (Stars / TON-нано / USDT-decimal)
автоматически идёт в призовой пул соответствующей валюты». Use-case вызывается
из flow `SpinPaidRoulette` (4.1-B / Шаг B.5) **сразу после** успешного
`IPaymentLedger.charge(...)` подтверждённого платежа — внутри той же
транзакции UoW, чтобы пул-инкремент и платёж были атомарны (без «потерянного
доната»).

Вычисление дельты — `floor`-округление: `donation_amount_native =
payment_amount_native // _DONATION_DIVISOR`. ГДД-§12.6.1 не указывает
правило округления при `amount % 10 != 0`; решено стартовать с `floor`-варианта
(в пользу платформы — пользователь не теряет ничего, потому что платит
ровно столько, сколько списано в Telegram). При фидбеке на review этот
делитель / правило округления могут поменяться (см. `current_tasks.md`,
секция «Известные блокеры»).

`donation == 0` (платежи `<10` native-юнитов) — фильтруется на уровне
use-case: `apply_increment` не вызывается, в результате стоит `applied=False`,
а `pool_after` берётся через `IPrizePoolRepository.get_current()`.
Это эквивалент no-op-инкремента и сохраняет инвариант «нет нулевых-дельт
в audit-логе» (audit-запись пула будет добавлена в B.4 — там же
`AuditSource.PRIZE_POOL_INCREMENT` и whitelist-расширение).

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

Не-side-effect-ы:

* В B.2 (этот шаг) audit **не пишется**. Audit-запись (`AuditAction.
  PRIZE_POOL_INCREMENT`, `AuditSource.PRIZE_POOL_INCREMENT`) добавится
  в B.4 (там же — Alembic-миграция, расширяющая `audit_log_source_whitelist`).
* В B.2 нет ORM-репозитория — порт `IPrizePoolRepository` — Protocol,
  fake-реализация в тестах. Реальная `SqlAlchemyPrizePoolRepository` +
  таблица `prize_pool_balance` появятся в B.3.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.monetization.entities import PrizePool
from pipirik_wars.domain.monetization.ports import IPrizePoolRepository
from pipirik_wars.domain.monetization.value_objects import Currency, IdempotencyKey

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
    """Use-case: 10% подтверждённого платежа → призовой пул.

    Архитектура (ГДД §0): чистый application-слой, без UoW (caller
    оборачивает в `async with self._uow`), без записи аудита (B.2),
    без побочных Telegram-вызовов. Только репозиторий пула + чистая
    арифметика.
    """

    __slots__ = ("_pool_repo",)

    def __init__(self, *, prize_pool_repository: IPrizePoolRepository) -> None:
        """DI-конструктор.

        Args:
            prize_pool_repository: порт репозитория призового пула
                (`IPrizePoolRepository`). На 4.1-B (Шаг B.2) — fake
                in-memory; реальная `SqlAlchemyPrizePoolRepository`
                появится в B.3.
        """
        self._pool_repo = prize_pool_repository

    async def execute(self, command: RecordDonationCommand) -> RecordDonationResult:
        """Выполнить расчёт + инкремент пула.

        Шаги:

        1. Вычислить `donation = command.payment_amount_native // 10`
           (`floor`-округление, ГДД §12.6.1).
        2. Если `donation <= 0` — пропустить инкремент, вернуть текущий
           снапшот пула с `applied=False`.
        3. Иначе — `await self._pool_repo.apply_increment(currency, donation)`,
           вернуть свежий снапшот пула с `applied=True`.

        Контракт: вызывающий код отвечает за UoW-транзакцию. Любая
        ошибка из репозитория пробрасывается без catch-ов.
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
        return RecordDonationResult(
            donation_amount_native=donation_amount_native,
            pool_after=pool_after,
            applied=True,
        )
