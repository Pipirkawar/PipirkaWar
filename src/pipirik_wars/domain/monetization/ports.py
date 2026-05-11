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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pipirik_wars.domain.monetization.entities import (
    Payment,
    PaymentStatus,
    PrizeLot,
    PrizeLotStatus,
    PrizePool,
    Wallet,
)
from pipirik_wars.domain.monetization.value_objects import Currency, IdempotencyKey

__all__ = [
    "IFeeEstimator",
    "IPaymentLedger",
    "IPrizeLotRepository",
    "IPrizePoolRepository",
    "ITonConnectVerifier",
    "ITonPayoutAdapter",
    "IWalletRepository",
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


class IPrizePoolRepository(Protocol):
    """Порт репозитория призового пула (ГДД §12.6, Спринт 4.1-B).

    Призовой пул хранится одной строкой per-currency в таблице
    `prize_pool_balance` (миграция `0027_prize_pool_balance` —
    persistence создаётся в B.3). Репозиторий собирает строки в
    единый доменный VO `PrizePool(stars, ton_nano, usdt_decimal)` и
    отдаёт его use-case-ам монетизации.

    Все методы — асинхронные, выполняются в открытой `IUnitOfWork`-сессии.
    Композиционный root (`bot/main.py` Спринт 4.1-B) пробрасывает
    SQLAlchemy-implementation; тесты use-case-ов (`RecordDonation`) —
    `FakePrizePoolRepository` (in-memory pool с тем же контрактом).

    Семантика операций:

    * `get_current()` — снапшот всех трёх балансов одной транзакцией.
      На пустом пуле (свежезаведённая БД, до первого `apply_increment`)
      возвращает `PrizePool.empty()` (`stars=ton_nano=usdt_decimal=0`).
      Используется admin-handler-ом `/prize_pool` (4.1-E) и
      use-case-ом `RecordDonation` для построения `pool_after`-результата.
    * `apply_increment(currency, amount_native)` — атомарный inc/dec
      (`balance := balance + amount_native`, `>= 0`-инвариант). Реализация
      использует SQL `UPDATE prize_pool_balance SET balance_native =
      balance_native + :delta WHERE currency = :cur RETURNING ...`,
      что гарантирует атомарность под concurrent-writers (одна
      строка обновляется row-lock-ом в SERIALIZABLE / READ-COMMITTED).
      Возвращает свежий `PrizePool`-снапшот всех трёх балансов
      (после применения инкремента).

      Если `amount_native < 0` и `current_balance + amount_native < 0`
      — поднимает `PrizePoolAmountInvariantError` (last-line-of-defense
      на БД-стороне — CHECK-ограничение `ck_prize_pool_balance_native_non_negative`).
    """

    async def get_current(self) -> PrizePool:
        """Получить текущий снапшот пула (`PrizePool` по всем валютам).

        Идемпотентен (SELECT, без побочных эффектов). На пустой
        БД возвращает `PrizePool.empty()`.
        """
        ...

    async def apply_increment(
        self,
        *,
        currency: Currency,
        amount_native: int,
    ) -> PrizePool:
        """Атомарно увеличить (или уменьшить) баланс в указанной валюте.

        Параметры:
        - `currency` — какой балансовый счёт пула обновлять.
        - `amount_native` — дельта в native-юнитах. Может быть `0`
          (no-op), положительной (увеличить пул), отрицательной
          (уменьшить — будущие `withdraw`/`reset`-флоу 4.1-D/E).

        Возвращает: свежий `PrizePool`-снапшот всех трёх балансов
        после применения дельты.

        Поднимает `PrizePoolAmountInvariantError` если
        `current_balance + amount_native < 0`.
        """
        ...


class IPrizeLotRepository(Protocol):
    """Порт репозитория крипто-лотов (ГДД §12.6, Спринт 4.1-C).

    Лоты — нарезанные «куски» призового пула, сохранённые в таблице
    `prize_lots` (миграция `0029_prize_lots` — persistence создаётся в
    шаге C.3). Жизненный цикл — машина состояний `ACTIVE → RESERVED →
    CLAIMED|REFUNDED` (`PrizeLotStatus`).

    Все методы — асинхронные, выполняются в открытой `IUnitOfWork`-сессии.
    Композиционный root (`bot/main.py` Спринт 4.1-C, шаг C.9)
    пробрасывает SQLAlchemy-implementation; тесты use-case-ов
    (`GeneratePrizeLots` шаг C.2, picker C.5) — `FakePrizeLotRepository`
    (in-memory словарь с тем же контрактом).

    Семантика операций:

    * `add(lot)` — записать свежесгенерированный лот (с `id=None`,
      `status=ACTIVE`). Возвращает тот же лот, но с `id`, проставленным
      БД через `DEFAULT nextval('prize_lots_id_seq')`. Атомарность —
      одна `INSERT ... RETURNING id`.
    * `get_by_id(lot_id)` — точечный SELECT по id. На несуществующем
      id возвращает `None` (не бросает `PrizeLotNotFoundError` —
      caller сам решает, что делать с `None`).
    * `list_active(currency)` — все `status=ACTIVE`-лоты указанной
      валюты. Используется picker-ом крипто-приза (шаг C.5): из
      возвращённой коллекции picker берёт первый детерминированно
      (детерминизм — для аудита и для воспроизводимости в тестах).
      Пустой результат → picker должен выкатить fallback-исход
      (например, перенаправить в free-рулетку другой outcome,
      или `RouletteOutcomeKind.SCROLL`).
    * `update_status(lot_id, new_status, claimed_at?)` — атомарная
      смена статуса с проверкой исходного состояния. Реализация
      использует SQL `UPDATE prize_lots SET status=:new_status,
      claimed_at=:claimed_at WHERE id=:lot_id AND status IN (...)`,
      где `(...)` — `_PRIZE_LOT_TRANSITIONS[old_status]` для каждого
      возможного `old_status`. `rows_affected=1` → перешли; `0` →
      либо лота нет (`PrizeLotNotFoundError`), либо статус уже не тот
      (`PrizeLotStatusTransitionError` с `from_status` из текущего
      SELECT). Различение этих двух случаев — отдельный SELECT
      после неудачного `UPDATE`.

      На `new_status=CLAIMED` параметр `claimed_at` обязан быть
      выставлен; на остальных — игнорируется (или используется как
      «момент refund-а», если caller передал — это нормально).
    """

    async def add(self, *, lot: PrizeLot) -> PrizeLot:
        """Записать новый лот в `prize_lots`.

        Параметры:
        - `lot: PrizeLot` — с `id=None`, `status=ACTIVE`,
          `claimed_at=None` (свежесгенерированный через
          `PrizeLot.freshly_generated(...)`).

        Возвращает: тот же `PrizeLot`, но с `id`, проставленным БД.
        """
        ...

    async def get_by_id(self, *, lot_id: int) -> PrizeLot | None:
        """Получить лот по `id` или `None` (если не существует).

        Идемпотентен (SELECT, без побочных эффектов).
        """
        ...

    async def list_active(self, *, currency: Currency) -> Sequence[PrizeLot]:
        """Все `status=ACTIVE`-лоты указанной валюты.

        Порядок результата — стабильный (`ORDER BY id ASC` в SQL-
        реализации, для in-memory Fake — insertion order). Это нужно
        picker-у (шаг C.5) для детерминированного выбора лота.
        Пустой результат — нормально (если в пуле нет активных лотов
        этой валюты, picker делает fallback).
        """
        ...

    async def update_status(
        self,
        *,
        lot_id: int,
        new_status: PrizeLotStatus,
        claimed_at: datetime | None = None,
    ) -> PrizeLot:
        """Атомарно перевести лот в `new_status` с проверкой машины состояний.

        Параметры:
        - `lot_id` — id лота в `prize_lots`.
        - `new_status` — целевой статус (`RESERVED` / `CLAIMED` /
          `REFUNDED`; `ACTIVE` не валидный target — лоты в `ACTIVE`
          создаются через `add(...)`).
        - `claimed_at` — TZ-aware момент claim-а; обязателен на
          `new_status=CLAIMED`, на остальных — `None`.

        Возвращает: обновлённый `PrizeLot`-снапшот.

        Поднимает:
        - `PrizeLotNotFoundError` — если `lot_id` не существует.
        - `PrizeLotStatusTransitionError` — если текущий статус
          не разрешает переход в `new_status` (см.
          `_PRIZE_LOT_TRANSITIONS`).
        """
        ...


class IFeeEstimator(Protocol):
    """Порт оценки сетевой комиссии для лота (ГДД §12.6.3, Спринт 4.1-C).

    Зачем: при генерации лотов из `PrizePool` (`GeneratePrizeLots`,
    шаг C.2) сервис закладывает в каждый лот `fee_buffer_native` —
    запас на оплату gas-а при будущей выплате в TON / USDT-сети.
    Реальная комиссия меняется минута-к-минуте; буфер
    проксимируется P95-аппроксимацией газа за последние 7 дней.

    На 4.1-C реализация — in-memory константная (шаг C.8): возвращает
    fixed-значение per-currency, читаемое из `domain/balance/config.py`.
    На 4.1-D появится реальная имплементация на базе TON RPC
    (`InfrastructureFeeEstimator`), которая дёргает on-chain-API
    (`runGetMethod('getJettonData')` для USDT-jetton-фи / `tonapi.io`-
    эндпоинт для TON-передачи). Контракт порта — единый, реализации
    подменяемы через composition root.

    Все методы — асинхронные (на 4.1-D понадобится HTTP-вызов, поэтому
    на 4.1-C async-сигнатура — на вырост).

    Семантика:
    * STARS-валюта: всегда возвращает `0` (TG-сторона не берёт
      gas-а — комиссия TG Stars уже учтена в `payments`-таблице).
    * TON_NANO / USDT_DECIMAL: возвращает положительный или нулевой
      int — буфер в native-юнитах. Гарантирует `<= target_amount_native`
      не гарантирует (caller — `GeneratePrizeLots` — обязан сам
      проверить invariant `amount_native > fee_buffer_native`,
      иначе `PrizeLotInvariantError` на конструировании лота).
    """

    async def estimate_fee(
        self,
        *,
        currency: Currency,
        target_amount_native: int,
    ) -> int:
        """Оценить буфер комиссии для будущей выплаты лота.

        Параметры:
        - `currency` — валюта будущей выплаты.
        - `target_amount_native` — потенциальный размер лота в
          native-юнитах (`>= 1`). Используется на 4.1-D в подсказку
          fee-estimator-у (для больших переводов USDT-jetton-комиссия
          выше, чем для маленьких); на 4.1-C реализация игнорирует.

        Returns:
        - `int >= 0` — оценка буфера в native-юнитах. Для STARS —
          всегда `0`. Для TON_NANO / USDT_DECIMAL — позитивный
          (P95-аппроксимация газа).
        """
        ...


class IWalletRepository(Protocol):
    """Порт репозитория кошельков (ГДД §12.6.4, Спринт 4.1-D).

    Один игрок — один кошелёк per-currency. ``add_or_replace`` —
    upsert: если у игрока уже есть кошелёк данной валюты, адрес
    обновляется. Все методы — async, выполняются в ``IUnitOfWork``.
    """

    async def add_or_replace(self, *, wallet: Wallet) -> Wallet:
        """Upsert кошелёк: вставить или заменить адрес.

        Возвращает сохранённый ``Wallet``.
        """
        ...

    async def get_by_player_and_currency(
        self,
        *,
        player_id: int,
        currency: Currency,
    ) -> Wallet | None:
        """Получить кошелёк или ``None``."""
        ...


class ITonConnectVerifier(Protocol):
    """Порт верификации TON Connect proof (Спринт 4.1-D).

    Проверяет, что ``proof`` (подпись ``ton_proof``) действительно
    принадлежит ``address`` — защита от подмены адреса другим
    игроком. Реализация — infrastructure-слой (HTTP-вызов к
    TON Connect verification endpoint или локальная проверка).
    """

    async def verify(
        self,
        *,
        address: str,
        proof: str,
    ) -> bool:
        """``True`` если proof валидный для данного address."""
        ...


class ITonPayoutAdapter(Protocol):
    """Порт выплаты TON / USDT на кошелёк игрока (Спринт 4.1-D).

    Отправляет native-юниты ``amount_native`` валюты ``currency``
    на ``recipient_address``. Возвращает ``PayoutResult`` с
    ``tx_hash`` и ``actual_fee_native``.
    """

    async def payout(
        self,
        *,
        currency: Currency,
        amount_native: int,
        recipient_address: str,
    ) -> PayoutResult:
        """Выплатить приз. Возвращает ``PayoutResult``."""
        ...


@dataclass(frozen=True, slots=True)
class PayoutResult:
    """Результат выплаты через ``ITonPayoutAdapter`` (Спринт 4.1-D).

    * ``tx_hash: str`` — хэш транзакции в TON-сети.
    * ``actual_fee_native: int`` — фактическая комиссия в native-юнитах.
    """

    tx_hash: str
    actual_fee_native: int
