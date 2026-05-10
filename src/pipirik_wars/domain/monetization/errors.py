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

from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.shared.errors import DomainError

__all__ = [
    "IdempotencyConflictError",
    "MonetizationDomainError",
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
