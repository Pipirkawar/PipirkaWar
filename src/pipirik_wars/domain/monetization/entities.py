"""Доменные сущности монетизации (ГДД §12.5–§12.6, Спринт 4.1-A).

`PaymentStatus` — машинный enum статуса платежа (`PENDING` / `CONFIRMED`
/ `REFUNDED`); попадает в `payments.status` (CHECK-constraint
`payments_status_whitelist`) и в `audit_log.payload.status`. Значения
стабильные, не менять без миграции.

`Payment` — frozen-VO, доменное представление одной строки `payments`-
таблицы. Хранит «кто-сколько-в-какой-валюте-под-каким-ключом» одного
платёжного события. Identity на уровне домена эквивалентна
`(player_id, idempotency_key)` — повторный `IPaymentLedger.charge(...)`
с тем же `idempotency_key` возвращает существующий `Payment` (антифрод,
плана 4.1.4); коллизия суммы / игрока с тем же ключом —
`IdempotencyConflictError` (см. `errors.py`).

`amount_native: int` — сумма в минимальных единицах валюты:
* `Currency.STARS` → целое число ⭐ (`>= 1`);
* `Currency.TON_NANO` → нано-тонкоины (`int`, `1 TON = 10**9 nano-TON`);
* `Currency.USDT_DECIMAL` → минор-юниты USDT-jetton (`int`,
  `1 USDT = 10**6` единиц при `decimals=6`).

В Спринте 4.1-A создаются и обрабатываются только `STARS`-платежи;
`TON_NANO` / `USDT_DECIMAL` появятся в 4.1-D вместе с TON Connect.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from pipirik_wars.domain.monetization.errors import (
    PrizeLotInvariantError,
    PrizeLotStatusTransitionError,
    PrizePoolAmountInvariantError,
)
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    FeeBufferAmount,
    IdempotencyKey,
    StarsPoolBalance,
    TonAddress,
    TonNanoAmount,
    UsdtDecimalAmount,
    UsdtJettonAddress,
)

__all__ = [
    "Payment",
    "PaymentStatus",
    "PrizeLot",
    "PrizeLotStatus",
    "PrizePool",
    "Wallet",
]


class PaymentStatus(StrEnum):
    """Машинный статус платежа (ГДД §12.5.1, Спринт 4.1-A).

    `PENDING` — invoice выставлен, но `successful_payment` от Telegram
    ещё не пришёл (либо `pre_checkout_query` не завершён). По умолчанию —
    статус только что вставленной строки в `payments`-таблице.

    `CONFIRMED` — платёж подтверждён провайдером (для Telegram Stars —
    через `successful_payment`-callback в bot-handler-е, Спринт 4.1-A).
    Use-case `SpinPaidRoulette` начисляет приз только после
    `CONFIRMED`-статуса.

    `REFUNDED` — платёж возвращён игроку (например, через
    `/refund_lot`-админ-команду 4.1.10 или ручной refund от поддержки).
    Возврат ⭐ из ledger-а реализуется в 4.1-E (admin-handler-ы).

    Стабильные машинные id, не менять без миграции.
    """

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REFUNDED = "refunded"


@dataclass(frozen=True, slots=True)
class Payment:
    """Иммутабельная запись одного платёжного события (ГДД §12.5.1, Спринт 4.1-A).

    Доменное представление строки `payments`-таблицы. Хранит:

    * `player_id: int` — id игрока (FK → `users.id`).
    * `currency: Currency` — валюта платежа (`STARS` / `TON_NANO` /
      `USDT_DECIMAL`).
    * `amount_native: int` — сумма в минимальных единицах валюты
      (см. модуль-докстрингу). `>= 1` (защищено в `__post_init__`).
    * `idempotency_key: IdempotencyKey` — стабильный ключ дедупликации
      (валидирован VO `IdempotencyKey`). Хранится в БД-индексе
      `UNIQUE (player_id, idempotency_key)` (миграция `0026_payments`).
    * `status: PaymentStatus` — статус платежа (по умолчанию `PENDING`).
    * `provider_payment_id: str | None` — id платежа на стороне
      провайдера (`successful_payment.telegram_payment_charge_id`
      для TG Stars; `tx_hash` для TON в 4.1-D). На моменте `PENDING` —
      `None`, проставляется при переходе в `CONFIRMED`.
    * `created_at: datetime` — момент создания записи (TZ-aware).
    * `confirmed_at: datetime | None` — момент перехода в `CONFIRMED`
      (TZ-aware). На моменте `PENDING` / `REFUNDED` без подтверждения —
      `None`.
    * `payload: Mapping[str, str]` — провайдер-специфичный произвольный
      payload в read-only `MappingProxyType` (для TG Stars: `{"invoice_payload":
      "...", "tg_user_id": "..."}` etc.). По умолчанию — пустой
      MappingProxyType. На уровне БД хранится в JSONB-колонке `payments.payload`.

    Frozen + slots → VO без identity (на уровне домена две идентичные
    `Payment`-VO неотличимы; identity у строки в БД обеспечивается
    автоинкрементной `id`-колонкой ORM). Сравнение `==` — по полям.
    """

    player_id: int
    currency: Currency
    amount_native: int
    idempotency_key: IdempotencyKey
    status: PaymentStatus
    created_at: datetime
    provider_payment_id: str | None = None
    confirmed_at: datetime | None = None
    payload: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.player_id, int) or isinstance(self.player_id, bool):
            raise TypeError(
                f"Payment.player_id must be int, got {type(self.player_id).__name__}",
            )
        if self.player_id <= 0:
            raise ValueError(
                f"Payment.player_id must be > 0, got {self.player_id}",
            )
        if not isinstance(self.amount_native, int) or isinstance(self.amount_native, bool):
            raise TypeError(
                f"Payment.amount_native must be int, got {type(self.amount_native).__name__}",
            )
        if self.amount_native < 1:
            raise ValueError(
                f"Payment.amount_native must be >= 1, got {self.amount_native}",
            )
        if self.created_at.tzinfo is None:
            raise ValueError(
                "Payment.created_at must be timezone-aware "
                "(naïve datetime would lose UTC offset on persistence)",
            )
        if self.confirmed_at is not None and self.confirmed_at.tzinfo is None:
            raise ValueError(
                "Payment.confirmed_at must be timezone-aware",
            )
        if self.status is PaymentStatus.CONFIRMED:
            if self.confirmed_at is None:
                raise ValueError(
                    "Payment(status=CONFIRMED) requires confirmed_at to be set",
                )
            if self.provider_payment_id is None:
                raise ValueError(
                    "Payment(status=CONFIRMED) requires provider_payment_id to be set",
                )
        if self.status is PaymentStatus.PENDING and self.confirmed_at is not None:
            raise ValueError(
                f"Payment(status=PENDING) must have confirmed_at=None, got {self.confirmed_at!r}",
            )


@dataclass(frozen=True, slots=True)
class PrizePool:
    """Иммутабельный агрегат «призовой пул» (ГДД §12.6, Спринт 4.1-B).

    ГДД §12.6 «Призовой пул и лотерея» определяет пул как
    «тры отдельных баланса по валютам (Stars / TON / USDT)» — именно
    это и хранит `PrizePool`. Поля:

    * `stars: StarsPoolBalance` — баланс ⋆ в пуле (`>= 0`).
    * `ton_nano: TonNanoAmount` — баланс нано-тонкоинов в пуле
      (`>= 0`; `1 TON = 10**9 nano-TON`).
    * `usdt_decimal: UsdtDecimalAmount` — баланс минор-юнит USDT-jetton
      в пуле (`>= 0`; `1 USDT = 10**6` юнит при `decimals=6`).

    Frozen + slots → агрегат без identity на доменном уровне
    (два идентичных снапшота пула неотличимы; identity хранит БД
    через первичный ключ ORM-строк `prize_pool_balance`-таблицы).
    Иммутабельность обязательна: «после +10 ⋆» — это новый
    `PrizePool` (вид `apply_increment`); старый остаётся в прежнем
    состоянии (важно для «без побочных эффектов»-тестов).
    """

    stars: StarsPoolBalance
    ton_nano: TonNanoAmount
    usdt_decimal: UsdtDecimalAmount

    @classmethod
    def empty(cls) -> PrizePool:
        """Фабричный метод «пустой пул» (`stars=0, ton_nano=0, usdt_decimal=0`).

        Используется в unit-тестах use-case-ов и в seed-логике
        первого прогона миграции `0027` (3 роу по per-currency).
        """
        return cls(
            stars=StarsPoolBalance(0),
            ton_nano=TonNanoAmount(0),
            usdt_decimal=UsdtDecimalAmount(0),
        )

    def balance_for(self, currency: Currency) -> int:
        """Вернуть баланс в native-юнитах для указанной `Currency`.

        Полезно в use-case-ах (`RecordDonation` проверяет «пул вырос
        на N») и в admin-handler-ах (`/prize_pool` печатает все балансы).
        """
        if currency is Currency.STARS:
            return self.stars.value
        if currency is Currency.TON_NANO:
            return self.ton_nano.value
        if currency is Currency.USDT_DECIMAL:
            return self.usdt_decimal.value
        # `Currency` — StrEnum, исчерпывающий case-анализ выше; эта строка
        # не должна быть достижима в рантайме при хороших инвариантах;
        # mypy видит её как `unreachable` (или «return-ветка отсутствует»,
        # если опустить).
        raise AssertionError(f"unreachable: unknown Currency {currency!r}")

    def apply_increment(self, currency: Currency, amount_native: int) -> PrizePool:
        """Иммутабельный инкремент баланса в валюте `currency`.

        Правила:

        * `amount_native` — `int`, разрешает отрицательное значение
          (для будущих выводов в 4.1-D / 4.1-E или admin-`reset`-операции).
        * Результат `balance_for(currency) + amount_native` обязан быть
          `>= 0`. Иначе — `PrizePoolAmountInvariantError`. На 4.1-B
          use-case `RecordDonation` вызывает этот метод только
          с `amount_native >= 0`, но инвариант сторожит будущие
          выводы / рефакторинги.
        * Возвращает новый `PrizePool`-инстанс (старый не мутируется).
          Аналогично конвенции `domain/roulette/entities.py::RouletteOutcome.with_*`.

        Инфраструктура-репозиторий (`SqlAlchemyPrizePoolRepository`)
        реализует atomic-инкремент через SQL `UPDATE ... RETURNING`,
        этот же метод — иммутабельный доменный эквивалент для Fake-
        имплементации (in-memory pool в unit-тестах use-case-ов).
        """
        if not isinstance(amount_native, int) or isinstance(amount_native, bool):
            raise TypeError(
                f"PrizePool.apply_increment.amount_native must be int, "
                f"got {type(amount_native).__name__}",
            )
        current = self.balance_for(currency)
        new_value = current + amount_native
        if new_value < 0:
            raise PrizePoolAmountInvariantError(
                currency=currency,
                current_balance_native=current,
                attempted_delta_native=amount_native,
            )
        if currency is Currency.STARS:
            return PrizePool(
                stars=StarsPoolBalance(new_value),
                ton_nano=self.ton_nano,
                usdt_decimal=self.usdt_decimal,
            )
        if currency is Currency.TON_NANO:
            return PrizePool(
                stars=self.stars,
                ton_nano=TonNanoAmount(new_value),
                usdt_decimal=self.usdt_decimal,
            )
        if currency is Currency.USDT_DECIMAL:
            return PrizePool(
                stars=self.stars,
                ton_nano=self.ton_nano,
                usdt_decimal=UsdtDecimalAmount(new_value),
            )
        # Недостижимо при исчерпывающем case-анализе `Currency`-StrEnum.
        raise AssertionError(f"unreachable: unknown Currency {currency!r}")


class PrizeLotStatus(StrEnum):
    """Машинный статус лота крипто-приза (ГДД §12.6, Спринт 4.1-C).

    `ACTIVE` — свежесгенерированный лот, доступен для выпадения в
    результат-пуле free + paid рулеток (picker, шаг C.5). Default-статус
    после `IPrizeLotRepository.add(...)`.

    `RESERVED` — лот занят конкретным игроком после сработки в спине;
    выплата отложена до `ClaimPrize` (4.1-D). Не возвращается в picker.
    Переход `ACTIVE → RESERVED` атомарный (`UPDATE ... WHERE
    status='active'`-row-lock) — защищает от race-condition «два
    игрока попали в один лот».

    `CLAIMED` — игрок забрал приз через `ClaimPrize` (4.1-D); транзакция
    в TON / USDT-сети успешна. Terminal-статус: `claimed_at` помечается,
    `update_status` дальше не разрешён.

    `REFUNDED` — лот возвращён в пул (например, `actual_fee > fee_buffer`
    при выводе, или admin-команда `/refund_lot` 4.1-E). Terminal-статус.
    Сумма лота вычтена обратно в `PrizePool`-балансе отдельным шагом
    use-case-а — этот enum только маркирует жизненный цикл лота.

    Стабильные машинные id, попадают в `prize_lots.status` (CHECK-constraint
    миграция 4.1-C `0029_prize_lots`) и в `audit_log.payload.lot_status`.
    Не менять без миграции.
    """

    ACTIVE = "active"
    RESERVED = "reserved"
    CLAIMED = "claimed"
    REFUNDED = "refunded"


# Разрешённые переходы машины состояний лота (см. PrizeLotStatus-docstring).
# `frozenset()` под terminal-статус — формальный знак «выходов нет».
# Доступно как read-only `MappingProxyType` — снаружи модифицировать
# нельзя (попытка добавить ключ → TypeError).
_PRIZE_LOT_TRANSITIONS: Mapping[PrizeLotStatus, frozenset[PrizeLotStatus]] = MappingProxyType(
    {
        PrizeLotStatus.ACTIVE: frozenset(
            {PrizeLotStatus.RESERVED, PrizeLotStatus.REFUNDED},
        ),
        PrizeLotStatus.RESERVED: frozenset(
            {PrizeLotStatus.CLAIMED, PrizeLotStatus.REFUNDED},
        ),
        PrizeLotStatus.CLAIMED: frozenset(),
        PrizeLotStatus.REFUNDED: frozenset(),
    },
)


@dataclass(frozen=True, slots=True)
class PrizeLot:
    """Иммутабельный агрегат «лот крипто-приза» (ГДД §12.6, Спринт 4.1-C).

    Лот — это нарезанный кусок призового пула `PrizePool`, заведённый
    application-сервисом `GeneratePrizeLots` (шаг C.2) под выдачу в
    результат-пуле рулеток. Жизненный цикл лота — машина состояний
    `ACTIVE → RESERVED → CLAIMED|REFUNDED`, см. `PrizeLotStatus`.

    Поля:

    * `id: int | None` — id строки в `prize_lots`-таблице.
      На свежесозданном (in-memory) лоте — `None`; после
      `IPrizeLotRepository.add(...)` — `int > 0`. Convention
      идентична `domain/caravan/entities.py::Caravan.id`.
    * `currency: Currency` — валюта лота (`STARS` / `TON_NANO` /
      `USDT_DECIMAL`). В рамках одной валюты лоты независимы
      друг от друга (один игрок может зарезервировать несколько
      лотов разных валют).
    * `amount_native: int` — размер приза в минимальных единицах
      валюты (`>= 1`, валидируется через invariant `amount_native >
      fee_buffer_native`). На уровне БД — `NUMERIC(38, 0)` (4.1-C
      миграция `0029`).
    * `fee_buffer_native: FeeBufferAmount` — заложенный буфер на
      оплату сетевой комиссии (`>= 0`, валидируется VO). На моменте
      `CLAIMED` фактическая комиссия может быть `<= fee_buffer_native`
      (игрок получает остаток); при `actual_fee > fee_buffer_native`
      лот переводится в `REFUNDED`, сумма возвращается в пул (4.1-D
      `ClaimPrize`-flow).
    * `status: PrizeLotStatus` — текущий статус (см. enum-docstring).
    * `created_at: datetime` — момент `IPrizeLotRepository.add(...)`
      (TZ-aware; валидируется).
    * `reserved_at: datetime | None` — момент резервирования (TZ-aware).
      На `ACTIVE` — `None`. На `RESERVED` — обязан быть выставлен.
      На `CLAIMED` — сохраняется из `RESERVED` (референс на момент
      брони; D.9-flow использует для expire-cron-а `now - reserved_at
      > reserved_ttl_seconds`). На `REFUNDED` — `None` если лот пришёл
      из `ACTIVE` (admin /refund_lot, 4.1-E); выставлен если из `RESERVED`
      (timeout-refund, 4.1-D D.9).
    * `claimed_at: datetime | None` — момент `ClaimPrize` (TZ-aware).
      На моменте `ACTIVE` / `RESERVED` / `REFUNDED` — `None`. На моменте
      `CLAIMED` — обязан быть выставлен (валидируется).

    Invariants:
    1. `amount_native > fee_buffer_native >= 0` — после удержания комиссии
       игроку обязан остаться `>= 1` минимальная единица валюты.
    2. `status == CLAIMED ⇒ claimed_at is not None` (и наоборот:
       `claimed_at is not None ⇒ status == CLAIMED`).
    3. `status == ACTIVE ⇒ reserved_at is None`; `status == RESERVED
       ⇒ reserved_at is not None`. Для `CLAIMED` / `REFUNDED` поле может
       быть любым (зависит от пути в state-machine).
    4. Status transition: `ACTIVE → RESERVED|REFUNDED`,
       `RESERVED → CLAIMED|REFUNDED`, `CLAIMED|REFUNDED` — terminal.
       Нарушение → `PrizeLotStatusTransitionError`.

    Frozen + slots → агрегат без мутаций; `reserve(...)` / `claim(...)` /
    `refund()` возвращают новый инстанс (старый не мутируется).
    Convention идентична `domain/caravan/entities.py::Caravan.mark_*`.
    """

    id: int | None
    currency: Currency
    amount_native: int
    fee_buffer_native: FeeBufferAmount
    status: PrizeLotStatus
    created_at: datetime
    reserved_at: datetime | None = None
    claimed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.amount_native, int) or isinstance(
            self.amount_native,
            bool,
        ):
            raise TypeError(
                f"PrizeLot.amount_native must be int, got {type(self.amount_native).__name__}",
            )
        if self.amount_native <= self.fee_buffer_native.value:
            raise PrizeLotInvariantError(
                currency=self.currency,
                amount_native=self.amount_native,
                fee_buffer_native=self.fee_buffer_native.value,
            )
        if self.created_at.tzinfo is None:
            raise ValueError(
                "PrizeLot.created_at must be timezone-aware "
                "(naïve datetime would lose UTC offset on persistence)",
            )
        if self.reserved_at is not None and self.reserved_at.tzinfo is None:
            raise ValueError(
                "PrizeLot.reserved_at must be timezone-aware",
            )
        if self.status is PrizeLotStatus.ACTIVE and self.reserved_at is not None:
            raise ValueError(
                f"PrizeLot(status=ACTIVE) must have reserved_at=None, got {self.reserved_at!r}",
            )
        if self.status is PrizeLotStatus.RESERVED and self.reserved_at is None:
            raise ValueError(
                "PrizeLot(status=RESERVED) requires reserved_at to be set",
            )
        if self.claimed_at is not None and self.claimed_at.tzinfo is None:
            raise ValueError(
                "PrizeLot.claimed_at must be timezone-aware",
            )
        if self.status is PrizeLotStatus.CLAIMED and self.claimed_at is None:
            raise ValueError(
                "PrizeLot(status=CLAIMED) requires claimed_at to be set",
            )
        if self.status is not PrizeLotStatus.CLAIMED and self.claimed_at is not None:
            raise ValueError(
                f"PrizeLot(status={self.status.value!r}) must have "
                f"claimed_at=None, got {self.claimed_at!r}",
            )
        if self.id is not None and (
            not isinstance(self.id, int) or isinstance(self.id, bool) or self.id <= 0
        ):
            raise ValueError(
                f"PrizeLot.id must be a positive int or None, got {self.id!r}",
            )

    @classmethod
    def freshly_generated(
        cls,
        *,
        currency: Currency,
        amount_native: int,
        fee_buffer_native: FeeBufferAmount,
        created_at: datetime,
    ) -> PrizeLot:
        """Свежесгенерированный лот — `id=None, status=ACTIVE, claimed_at=None`.

        Используется application-сервисом `GeneratePrizeLots` (шаг C.2)
        перед `IPrizeLotRepository.add(...)`. После `add(...)` репозиторий
        вернёт тот же лот, но с `id`, проставленным БД через DEFAULT-
        `nextval('prize_lots_id_seq')`.
        """
        return cls(
            id=None,
            currency=currency,
            amount_native=amount_native,
            fee_buffer_native=fee_buffer_native,
            status=PrizeLotStatus.ACTIVE,
            created_at=created_at,
            reserved_at=None,
            claimed_at=None,
        )

    @property
    def is_active(self) -> bool:
        """Лот активен — доступен в picker-е (шаг C.5)."""
        return self.status is PrizeLotStatus.ACTIVE

    @property
    def is_reserved(self) -> bool:
        """Лот зарезервирован за конкретным игроком до `ClaimPrize` (4.1-D)."""
        return self.status is PrizeLotStatus.RESERVED

    @property
    def is_terminal(self) -> bool:
        """Лот в terminal-статусе (`CLAIMED` / `REFUNDED`) — изменения не разрешены."""
        return self.status in (PrizeLotStatus.CLAIMED, PrizeLotStatus.REFUNDED)

    @property
    def net_amount_native(self) -> int:
        """Чистая сумма приза за вычетом fee-буфера (`amount_native -
        fee_buffer_native`). По invariant `>= 1`. На моменте `CLAIMED`
        используется в `ClaimPrize` (4.1-D) как сумма-к-переводу игроку,
        если фактическая комиссия попала в буфер.
        """
        return self.amount_native - self.fee_buffer_native.value

    def reserve(self, *, reserved_at: datetime) -> PrizeLot:
        """Перевести `ACTIVE → RESERVED` с пометкой времени резервирования.

        Используется на доменном уровне для in-memory моделирования
        резервирования (например, в Fake-репозитории unit-тестов).
        В production-flow атомарность гарантируется SQL-репозиторием
        (`UPDATE ... WHERE status='active'`, шаг C.3).

        `reserved_at` — TZ-aware момент резервирования (обычно
        `IClock.now()` из use-case-а спина). D.9-flow использует
        для expire-cron-а: если `now - reserved_at > reserved_ttl_seconds`
        (баланс-конфиг D.9.a), лот возвращается в `REFUNDED` + сумма
        в пул.
        """
        if reserved_at.tzinfo is None:
            raise ValueError(
                "PrizeLot.reserve(reserved_at=...) must be timezone-aware",
            )
        if self.status is not PrizeLotStatus.ACTIVE:
            raise PrizeLotStatusTransitionError(
                lot_id=self.id,
                from_status=self.status,
                to_status=PrizeLotStatus.RESERVED,
            )
        return PrizeLot(
            id=self.id,
            currency=self.currency,
            amount_native=self.amount_native,
            fee_buffer_native=self.fee_buffer_native,
            status=PrizeLotStatus.RESERVED,
            created_at=self.created_at,
            reserved_at=reserved_at,
            claimed_at=None,
        )

    def claim(self, *, claimed_at: datetime) -> PrizeLot:
        """Перевести `RESERVED → CLAIMED` с пометкой времени выплаты.

        Используется в use-case `ClaimPrize` (4.1-D) после успешной
        TON / USDT-транзакции.
        """
        if claimed_at.tzinfo is None:
            raise ValueError(
                "PrizeLot.claim(claimed_at=...) must be timezone-aware",
            )
        if self.status is not PrizeLotStatus.RESERVED:
            raise PrizeLotStatusTransitionError(
                lot_id=self.id,
                from_status=self.status,
                to_status=PrizeLotStatus.CLAIMED,
            )
        return PrizeLot(
            id=self.id,
            currency=self.currency,
            amount_native=self.amount_native,
            fee_buffer_native=self.fee_buffer_native,
            status=PrizeLotStatus.CLAIMED,
            created_at=self.created_at,
            reserved_at=self.reserved_at,
            claimed_at=claimed_at,
        )

    def refund(self) -> PrizeLot:
        """Перевести лот в `REFUNDED` (доступен из `ACTIVE` или `RESERVED`).

        Используется когда:
        * `actual_fee > fee_buffer_native` при попытке выплаты (4.1-D);
        * admin-команда `/refund_lot` (4.1-E);
        * лот «истёк» и не был забран (cron, опционально 4.1-E).

        Сумма лота возвращается в `PrizePool` отдельным шагом use-case-а
        (`PrizePoolService.apply_increment(currency, +amount_native)`).
        """
        return self._transition_to(PrizeLotStatus.REFUNDED)

    def _transition_to(self, new_status: PrizeLotStatus) -> PrizeLot:
        allowed = _PRIZE_LOT_TRANSITIONS[self.status]
        if new_status not in allowed:
            raise PrizeLotStatusTransitionError(
                lot_id=self.id,
                from_status=self.status,
                to_status=new_status,
            )
        return PrizeLot(
            id=self.id,
            currency=self.currency,
            amount_native=self.amount_native,
            fee_buffer_native=self.fee_buffer_native,
            status=new_status,
            created_at=self.created_at,
            reserved_at=self.reserved_at,
            claimed_at=self.claimed_at,
        )


@dataclass(frozen=True, slots=True)
class Wallet:
    """Привязанный TON-кошелёк игрока (ГДД §12.6.4, Спринт 4.1-D).

    Один игрок — один кошелёк per-currency (ГДД §12.6.5: «один
    TG-аккаунт = один TON-адрес для выплат»). При повторной привязке
    старый адрес заменяется (use-case ``LinkWallet``).

    Поля:

    * ``player_id: int`` — id игрока (FK → ``users.id``). ``> 0``.
    * ``address: str`` — строковый адрес кошелька. Конкретный
      формат зависит от ``currency``:

      - ``Currency.TON_NANO`` → raw / user-friendly TON-address
        (валидируется через ``TonAddress`` VO);
      - ``Currency.USDT_DECIMAL`` → raw / user-friendly TON-address
        (jetton-кошелёк; валидируется через ``UsdtJettonAddress`` VO);
      - ``Currency.STARS`` → не требуется (выплата Stars идёт через
        Telegram Bot API ``payments.refund`` на tg_id игрока;
        ``LinkWallet`` для Stars — `ValueError`).

    * ``currency: Currency`` — к какой валюте привязан адрес.
    * ``linked_at: datetime`` — TZ-aware момент привязки.

    Frozen + slots → VO / entity без мутаций. Identity на уровне
    домена — ``(player_id, currency)``. ``address`` может измениться
    при повторной привязке (``LinkWallet`` делает ``add_or_replace``).
    """

    player_id: int
    address: str
    currency: Currency
    linked_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.player_id, int) or isinstance(self.player_id, bool):
            raise TypeError(
                f"Wallet.player_id must be int, got {type(self.player_id).__name__}",
            )
        if self.player_id <= 0:
            raise ValueError(
                f"Wallet.player_id must be > 0, got {self.player_id}",
            )
        if not isinstance(self.address, str) or not self.address:
            raise ValueError(
                "Wallet.address must be a non-empty str",
            )
        if self.currency is Currency.STARS:
            raise ValueError(
                "Wallet does not support Currency.STARS — Stars payouts "
                "go through Telegram Bot API refund, no wallet needed",
            )
        if self.currency is Currency.TON_NANO:
            TonAddress(self.address)
        elif self.currency is Currency.USDT_DECIMAL:
            UsdtJettonAddress(self.address)
        if self.linked_at.tzinfo is None:
            raise ValueError(
                "Wallet.linked_at must be timezone-aware "
                "(naïve datetime would lose UTC offset on persistence)",
            )
