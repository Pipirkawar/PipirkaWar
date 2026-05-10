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

from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    IdempotencyKey,
)

__all__ = [
    "Payment",
    "PaymentStatus",
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
