"""Порты доменного слоя монетизации (ГДД §12.5–§12.6, Спринт 4.1-A).

Контракт чистый: реализация не видит ORM, не видит SQL — порт
оперирует только доменными VO / сущностями (`Currency`, `Payment`,
`IdempotencyKey`, `PaymentStatus`). Use-case `SpinPaidRoulette`
(Спринт 4.1-A, application-слой) пользуется только этим портом и
не знает про SQLAlchemy / Alembic.

`IPaymentLedger`:

* `charge(*, player_id, currency, amount_native, idempotency_key,
  status, occurred_at, provider_payment_id?, payload?)` — записать
  одну строку платежа в `payments`-таблицу. Дедуплицирует по
  `idempotency_key`:
    - первая вставка возвращает свежесозданный `Payment`;
    - повторный `charge(...)` с тем же `idempotency_key` и теми же
      `(player_id, currency, amount_native)` возвращает существующий
      `Payment` без побочных эффектов (honest retry, антифрод 4.1.4);
    - повторный `charge(...)` с тем же `idempotency_key`, но другой
      `(player_id | currency | amount_native)`-тройкой — поднимает
      `IdempotencyConflictError` (атака на double-charge или баг в
      bot-handler-е, который сгенерировал ключ без учёта payload-а).
* `get_by_idempotency_key(*, idempotency_key)` — вернуть существующую
  запись или `None`. Use-case `SpinPaidRoulette` использует это для
  раскопки оригинального `Payment.id` при retry-е (например, для
  повторной выдачи приза, если первая транзакция упала после `charge`-а).

Все методы — асинхронные, выполняются внутри открытой `IUnitOfWork`-сессии.
Композиционный root (`bot/main.py` Спринт 4.1-A) пробрасывает
SQLAlchemy-implementation; тесты use-case-ов (Спринт 4.1-A) —
`FakePaymentLedger`.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from pipirik_wars.domain.monetization.entities import Payment, PaymentStatus
from pipirik_wars.domain.monetization.value_objects import Currency, IdempotencyKey

__all__ = [
    "IPaymentLedger",
]


class IPaymentLedger(Protocol):
    """Порт ledger-а платежей (ГДД §12.5.1, антифрод 4.1.4).

    Все методы — асинхронные, выполняются в открытой `IUnitOfWork`-сессии.
    Композиционный root (`bot/main.py`) пробрасывает SQLAlchemy-impl;
    тесты use-case-ов — `FakePaymentLedger`.

    Семантика записей — append-only: каждый платёж — отдельная строка,
    UPDATE-ы только в смысле `status: PENDING → CONFIRMED | REFUNDED`
    (последнее — в Спринтах 4.1-A→4.1-E, через `mark_confirmed` /
    `mark_refunded`-методы; пока на 4.1-A только `charge` и
    `get_by_idempotency_key` нужны use-case-у `SpinPaidRoulette`).
    Дедупликация — на уровне БД-индекса
    `UNIQUE (player_id, idempotency_key)` (миграция `0026_payments`).
    """

    async def charge(
        self,
        *,
        player_id: int,
        currency: Currency,
        amount_native: int,
        idempotency_key: IdempotencyKey,
        status: PaymentStatus,
        occurred_at: datetime,
        provider_payment_id: str | None = None,
        payload: Mapping[str, str] | None = None,
    ) -> Payment:
        """Записать одну строку платежа в `payments` (idempotent, дедупликация).

        Семантика дедупликации (антифрод 4.1.4):
        - **Honest retry** (первая вставка): метод вставляет новую
          строку и возвращает соответствующий `Payment`. `created_at`
          == `occurred_at`. Если `status == CONFIRMED`, `confirmed_at`
          == `occurred_at`; иначе `confirmed_at` == `None`.
        - **Honest retry** (повторный вызов с тем же `idempotency_key`
          и тем же `(player_id, currency, amount_native)`-tuple): метод
          возвращает существующий `Payment` без побочных эффектов.
          Поля `status` / `provider_payment_id` / `payload` могут
          отличаться у переданного и у сохранённого — реализация
          обязана вернуть **сохранённый** в БД `Payment` (state
          обновляется отдельным API-методом, который появится в 4.1-D).
        - **Конфликт** (повторный вызов с тем же `idempotency_key`, но
          другим `player_id | currency | amount_native`): метод
          поднимает `IdempotencyConflictError` со всеми атрибутами
          существующего и попытавшегося платежа.

        Не путать с `IIdempotencyKey.is_seen()` / `mark()` (Спринт 1.6.D):
        тот порт работает в шлаге namespace-канал-`idempotency_keys`-таблицы
        для общей идемпотентности use-case-ов; `IPaymentLedger.charge` —
        специализированная идемпотентность поверх `payments`-таблицы.
        Use-case `SpinPaidRoulette` использует **оба**: `IIdempotencyKey`
        для общего «уже ли мы крутили эту рулетку» и `IPaymentLedger`
        для «уже ли мы записали этот платёж в ledger».

        Параметры:
        - `player_id` — id игрока (FK → `users.id`). `> 0` (валидируется
          в `Payment.__post_init__`).
        - `currency` — валюта платежа (`Currency.STARS` для 4.1-A;
          `TON_NANO` / `USDT_DECIMAL` появятся в 4.1-D).
        - `amount_native` — сумма в минимальных единицах валюты
          (`>= 1`; валидируется в `Payment.__post_init__`).
        - `idempotency_key` — ключ дедупликации (валидирован VO
          `IdempotencyKey`).
        - `status` — стартовый статус платежа (`PENDING` или `CONFIRMED`).
          На 4.1-A use-case `SpinPaidRoulette` пишет `PENDING` сразу
          после `pre_checkout_query` и `CONFIRMED` после `successful_payment`-callback.
          На 4.1-A `pre_checkout_query` пишет `PENDING` без
          `provider_payment_id`, а `successful_payment` обновляет
          через `mark_confirmed` (появится в 4.1-D вместе с TON-flow).
        - `occurred_at` — момент платежа (TZ-aware).
        - `provider_payment_id` — id платежа на стороне провайдера
          (`successful_payment.telegram_payment_charge_id` для TG Stars).
          На моменте `PENDING` обычно `None`.
        - `payload` — провайдер-специфичный произвольный payload
          (`{"invoice_payload": "...", ...}`); сохраняется в JSONB-колонке
          `payments.payload`. На моменте `PENDING` обычно `None`
          (записывается в `successful_payment`-callback).

        Returns:
        - `Payment` — либо свежевставленная, либо существующая запись.

        Raises:
        - `IdempotencyConflictError` — если ключ уже занят, но с другой
          `(player_id | currency | amount_native)`-тройкой (антифрод).
        - `pipirik_wars.shared.errors.IntegrityError` — если `player_id`
          ссылается на несуществующего игрока (FK violation).
        """
        ...

    async def get_by_idempotency_key(
        self,
        *,
        idempotency_key: IdempotencyKey,
    ) -> Payment | None:
        """Вернуть `Payment` по `idempotency_key` или `None`.

        Используется use-case-ом `SpinPaidRoulette` (Спринт 4.1-A) для
        восстановления оригинального `Payment` при retry-е (например,
        если первая транзакция упала между `charge`-ом и записью
        spin-ов в `roulette_spins`). На 4.1-A use-case всегда вызывает
        `charge` (он сам идемпотентен), но в 4.1-D этот метод понадобится
        `successful_payment`-handler-у — он вызывает `get_by_idempotency_key`
        перед обновлением `status`-а через будущий `mark_confirmed`-метод.

        Реализуется через `SELECT ... FROM payments WHERE
        idempotency_key = :key LIMIT 1` (B-tree индекс по
        `idempotency_key`, см. ORM-таблицу).
        """
        ...
