"""Domain-errors монетизации (ГДД §12.5–§12.6, Спринт 4.1-A).

Все наследуют общий `MonetizationDomainError` (он же — `DomainError`
из `pipirik_wars.shared.errors`), чтобы в use-case-ах 4.1-A/B/D и в
bot-handler-ах 4.1-A было удобно ловить «всё, что относится к платежам»
одним `except MonetizationDomainError`.

Спринт 4.1-A: `IdempotencyConflictError` (антифрод 4.1.4 — попытка
зарегистрировать платёж с уже занятым `idempotency_key`, но другой
суммой / валютой / игроком). Не путать с «повторным вызовом с тем же
ключом и теми же атрибутами» — это honest retry, и `IPaymentLedger.charge(...)`
обязан вернуть существующий receipt без побочного эффекта.

`InsufficientLengthForPaidRouletteError` / антифрод-ошибки могут
появиться в 4.1-D вместе с `IPaymentLedger.refund(...)` (refund-flow);
здесь их пока нет.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.shared.errors import DomainError

if TYPE_CHECKING:
    from pipirik_wars.domain.monetization.entities import PrizeLotStatus

__all__ = [
    "IdempotencyConflictError",
    "InvalidStarsPayloadError",
    "MonetizationDomainError",
    "PrizeLotInvariantError",
    "PrizeLotNotFoundError",
    "PrizeLotStatusTransitionError",
    "PrizePoolAmountInvariantError",
    "WalletAlreadyLinkedError",
    "WalletNotLinkedError",
]


class MonetizationDomainError(DomainError):
    """База для всех ошибок доменного слоя монетизации.

    Не бросается напрямую — у каждого случая есть свой подкласс.
    """


class IdempotencyConflictError(MonetizationDomainError):
    """Коллизия `idempotency_key` с другой суммой / валютой / игроком (4.1.4).

    Бросается портом `IPaymentLedger.charge(...)` (Спринт 4.1-A) когда
    игрок (или антифрод-злоумышленник) пытается зарегистрировать
    «новый» платёж под уже существующим `idempotency_key`, но с другой
    `(player_id, currency, amount_native)`-тройкой. Это потенциальная
    атака на double-charge или аккуратная защита от race-condition в
    Telegram-callback-е (`pre_checkout_query` / `successful_payment`
    могут прийти несколько раз — но обязаны нести одинаковый
    `invoice_payload` / `idempotency_key`).

    Аттрибуты — для машинной обработки и подстановки в локали:

    - `idempotency_key: str` — конфликтующий ключ.
    - `existing_player_id: int` — id игрока, на которого ключ был
      зарегистрирован первым.
    - `existing_currency: Currency` — валюта существующего платежа.
    - `existing_amount_native: int` — сумма существующего платежа
      (в минимальных единицах валюты).
    - `attempted_player_id: int` — id игрока, попытавшегося
      «перебить» существующую запись.
    - `attempted_currency: Currency` — валюта попытки.
    - `attempted_amount_native: int` — сумма попытки.
    """

    def __init__(
        self,
        *,
        idempotency_key: str,
        existing_player_id: int,
        existing_currency: Currency,
        existing_amount_native: int,
        attempted_player_id: int,
        attempted_currency: Currency,
        attempted_amount_native: int,
    ) -> None:
        self.idempotency_key = idempotency_key
        self.existing_player_id = existing_player_id
        self.existing_currency = existing_currency
        self.existing_amount_native = existing_amount_native
        self.attempted_player_id = attempted_player_id
        self.attempted_currency = attempted_currency
        self.attempted_amount_native = attempted_amount_native
        super().__init__(
            f"idempotency_key {idempotency_key!r} conflict: "
            f"existing player={existing_player_id} "
            f"currency={existing_currency.value} "
            f"amount={existing_amount_native}; "
            f"attempted player={attempted_player_id} "
            f"currency={attempted_currency.value} "
            f"amount={attempted_amount_native}",
        )


class PrizePoolAmountInvariantError(MonetizationDomainError):
    """Попытка увести баланс пула ниже нуля (ГДД §12.6, Спринт 4.1-B).

    Бросается из `PrizePool.apply_increment(currency, amount_native)`,
    когда `current_balance + amount_native < 0`. На 4.1-B use-case
    `RecordDonation` вызывает этот метод только с
    неотрицательным инкрементом, но инвариант сторожит будущие
    `withdraw`-/`reset`-флоу (4.1-D / 4.1-E) от «увести в минус»-багов.

    Параллельный last-line-of-defense — CHECK-ограничение
    `ck_prize_pool_balance_native_non_negative` на БД-стороне (миграция
    `0027`). Эта доменная ошибка срабатывает раньше (в unit-тестах
    use-case-а), БД-CHECK — последний рубеж при прямых SQL-правках.

    Аттрибуты для машинной обработки и подстановки в локали:

    - `currency: Currency` — валюта, баланс которой пытался
      уйти в минус.
    - `current_balance_native: int` — баланс до попытки инкремента
      (`>= 0`).
    - `attempted_delta_native: int` — попытанная дельта (`< 0`,
      иначе ошибка бы не возникла).
    """

    def __init__(
        self,
        *,
        currency: Currency,
        current_balance_native: int,
        attempted_delta_native: int,
    ) -> None:
        self.currency = currency
        self.current_balance_native = current_balance_native
        self.attempted_delta_native = attempted_delta_native
        super().__init__(
            f"PrizePool[{currency.value}] balance invariant violated: "
            f"current={current_balance_native}, "
            f"attempted_delta={attempted_delta_native}, "
            f"would-become={current_balance_native + attempted_delta_native} (< 0)",
        )


class PrizeLotInvariantError(MonetizationDomainError):
    """Нарушен инвариант `amount_native > fee_buffer_native >= 0` (Спринт 4.1-C).

    Бросается из `PrizeLot.__post_init__`, когда при построении лота
    в application-сервисе `GeneratePrizeLots` (шаг C.2) оказывается, что
    размер приза не превышает оценку комиссии (`amount_native <=
    fee_buffer_native`) — вывод такого лота оставил бы игрока без
    чистого приза. ГДД §12.6.3 требует: «minLot ≥ 1 USD-экв + комиссия»,
    то есть `amount_native >= fee_buffer_native + 1` (строго
    `amount_native > fee_buffer_native`).

    Параллельный last-line-of-defense — CHECK-ограничение
    `ck_prize_lots_amount_greater_than_fee_buffer` на БД-стороне (миграция
    `0029_prize_lots`, шаг C.3).

    Аттрибуты для машинной обработки и подстановки в локали:

    - `currency: Currency` — валюта лота.
    - `amount_native: int` — попытанный размер приза.
    - `fee_buffer_native: int` — заданный fee-буфер.
    """

    def __init__(
        self,
        *,
        currency: Currency,
        amount_native: int,
        fee_buffer_native: int,
    ) -> None:
        self.currency = currency
        self.amount_native = amount_native
        self.fee_buffer_native = fee_buffer_native
        super().__init__(
            f"PrizeLot[{currency.value}] invariant violated: "
            f"amount_native ({amount_native}) must be > "
            f"fee_buffer_native ({fee_buffer_native}) "
            f"(net prize would be {amount_native - fee_buffer_native} <= 0)",
        )


class PrizeLotStatusTransitionError(MonetizationDomainError):
    """Невалидный переход машины состояний `PrizeLot` (Спринт 4.1-C).

    Разрешённые переходы: `ACTIVE → RESERVED|REFUNDED`,
    `RESERVED → CLAIMED|REFUNDED`. `CLAIMED|REFUNDED` — terminal-статусы
    (переходов нет). Любой другой переход → эта ошибка.

    Бросается из `PrizeLot.reserve()` / `claim(...)` / `refund()` и из
    `IPrizeLotRepository.update_status(...)` в production-flow (шаг C.3,
    когда SQL `UPDATE ... WHERE status=:from` вернёт `rows_affected=0`,
    но лот существует — значит статус уже другой, race-condition
    «третий игрок уже резервировал этот лот» — фоллбэк-решение в шаге C.6).

    Аттрибуты:
    - `lot_id: int | None` — id лота (для in-memory свежего лота — `None`,
      в production-flow после `add(...)` — `int > 0`).
    - `from_status: PrizeLotStatus` — статус до попытки перехода.
    - `to_status: PrizeLotStatus` — попытанный новый статус.
    """

    def __init__(
        self,
        *,
        lot_id: int | None,
        from_status: PrizeLotStatus,
        to_status: PrizeLotStatus,
    ) -> None:
        self.lot_id = lot_id
        self.from_status = from_status
        self.to_status = to_status
        lot_repr = f"id={lot_id}" if lot_id is not None else "id=<unsaved>"
        super().__init__(
            f"PrizeLot({lot_repr}) invalid status transition: "
            f"{from_status.value!r} → {to_status.value!r}",
        )


class PrizeLotNotFoundError(MonetizationDomainError):
    """Лот с таким `id` не найден в репозитории (Спринт 4.1-C).

    Бросается из `IPrizeLotRepository.update_status(lot_id=..., ...)`,
    когда в БД нет строки с таким `id` (неверный ID от caller-а:
    баг в use-case или подделка со стороны admin-команды 4.1-E).
    `update_status` особо отличает этот случай от
    `PrizeLotStatusTransitionError` (лот есть, но статус уже другой) —
    этот различие важно для admin-логирования (одно — баг/атака,
    другое — ожидаемый race-condition).

    Аттрибуты:
    - `lot_id: int` — искомый id.
    """

    def __init__(self, *, lot_id: int) -> None:
        self.lot_id = lot_id
        super().__init__(f"PrizeLot(id={lot_id}) not found")


class WalletNotLinkedError(MonetizationDomainError):
    """Игрок не привязал кошелёк для указанной валюты (Спринт 4.1-D).

    Бросается use-case-ом ``ClaimPrize``, когда игрок пытается забрать
    крипто-приз, но ``IWalletRepository.get_by_player_and_currency(...)``
    вернул ``None``.

    Аттрибуты:
    - ``player_id: int``
    - ``currency: Currency``
    """

    def __init__(self, *, player_id: int, currency: Currency) -> None:
        self.player_id = player_id
        self.currency = currency
        super().__init__(
            f"Player(id={player_id}) has no linked wallet for currency {currency.value!r}",
        )


class InvalidStarsPayloadError(MonetizationDomainError):
    """Telegram Stars `invoice_payload` не прошёл серверную верификацию (Спринт 4.1-D, шаг D.8).

    Бросается портом ``ITgStarsPayloadVerifier.verify(...)`` когда:

    * raw payload пуст / превышает 128-байтовый лимит Telegram;
    * payload-структура (`<prefix>:<pack>:<seed>:<hmac>`) malformed —
      неверный prefix, отсутствуют поля, плохо закодирован `seed` / `hmac`;
    * HMAC-подпись не совпадает с локально пересчитанной над
      `(provider_id, idempotency_key, amount, currency)`-кортежем —
      payload либо подделан, либо был выпущен для другой суммы /
      валюты / игрока. В обоих случаях use-case 4.1-A
      ``SpinPaidRoulette.execute(...)`` НЕ вызывается, платёж
      аудируется отдельной audit-записью (`STARS_PAYLOAD_VERIFICATION_FAILED`,
      audit-source добавляется в D.8.c), Telegram-callback тихо игнорируется
      на UI-уровне (не показываем игроку причину, чтобы не помогать
      reverse-engineering-у формата подписи).

    Аттрибуты — для machine-readable логирования / audit-payload-а
    (без реального содержимого payload-а, чтобы не утечь HMAC-байты
    в logs):

    * ``reason: str`` — короткий машинный код причины (``"empty"`` /
      ``"too_long"`` / ``"malformed"`` / ``"bad_pack"`` /
      ``"bad_seed"`` / ``"bad_hmac"`` / ``"hmac_mismatch"``). Используется
      для подбора метрики `tg_stars_payload_verification_failed_total`
      по labels.
    * ``payload_len: int`` — фактическая длина raw payload-а в байтах
      (``0`` если payload был ``None`` / non-str). Безопасно логируется.
    """

    def __init__(self, *, reason: str, payload_len: int) -> None:
        self.reason = reason
        self.payload_len = payload_len
        super().__init__(
            f"Invalid TG Stars invoice_payload: reason={reason!r}, payload_len={payload_len}",
        )


class WalletAlreadyLinkedError(MonetizationDomainError):
    """Кошелёк уже привязан и попытка привязки дублирует адрес (Спринт 4.1-D).

    Бросается use-case-ом ``LinkWallet``, когда игрок пытается
    привязать тот же самый адрес, который уже привязан.

    Аттрибуты:
    - ``player_id: int``
    - ``currency: Currency``
    - ``existing_address: str``
    """

    def __init__(
        self,
        *,
        player_id: int,
        currency: Currency,
        existing_address: str,
    ) -> None:
        self.player_id = player_id
        self.currency = currency
        self.existing_address = existing_address
        super().__init__(
            f"Player(id={player_id}) already has wallet "
            f"for currency {currency.value!r} "
            f"with same address {existing_address!r}",
        )
