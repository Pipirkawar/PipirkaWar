"""In-memory реализация `IPaymentLedger` для unit-тестов use-case-ов (Спринт 4.1-A).

Имитирует `SqlAlchemyPaymentLedger` (появится в A.5):

* `charge(...)` — append-only вставка в `rows`. Идемпотентность по
  `idempotency_key`:
    - первый вызов вставляет `Payment` и возвращает его;
    - повторный с тем же ключом и теми же
      `(player_id, currency, amount_native)` — no-op, возвращает
      сохранённый `Payment`;
    - повторный с тем же ключом, но другими
      `(player_id | currency | amount_native)` — `IdempotencyConflictError`
      (антифрод 4.1.4).
* `get_by_idempotency_key(...)` — линейный поиск по `rows`.

Использование:

    ledger = FakePaymentLedger()
    payment = await ledger.charge(
        player_id=42,
        currency=Currency.STARS,
        amount_native=1,
        idempotency_key=IdempotencyKey("paid_roulette:42:tg-charge-001"),
        status=PaymentStatus.CONFIRMED,
        occurred_at=datetime.now(UTC),
        provider_payment_id="tg-charge-001",
    )

Тесты use-case-а `SpinPaidRoulette` могут читать `ledger.rows` напрямую
для проверки append-only-семантики.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType

from pipirik_wars.domain.monetization.entities import Payment, PaymentStatus
from pipirik_wars.domain.monetization.errors import IdempotencyConflictError
from pipirik_wars.domain.monetization.ports import IPaymentLedger
from pipirik_wars.domain.monetization.value_objects import Currency, IdempotencyKey


@dataclass
class FakePaymentLedger(IPaymentLedger):
    """In-memory реализация для тестов use-case-ов."""

    rows: list[Payment] = field(default_factory=list)

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
        """Append-only вставка с идемпотентностью по `idempotency_key`."""
        for existing in self.rows:
            if existing.idempotency_key == idempotency_key:
                # Honest retry vs конфликт — сравниваем
                # `(player_id, currency, amount_native)`-тройку.
                if (
                    existing.player_id != player_id
                    or existing.currency != currency
                    or existing.amount_native != amount_native
                ):
                    raise IdempotencyConflictError(
                        idempotency_key=idempotency_key.value,
                        existing_player_id=existing.player_id,
                        existing_currency=existing.currency,
                        existing_amount_native=existing.amount_native,
                        attempted_player_id=player_id,
                        attempted_currency=currency,
                        attempted_amount_native=amount_native,
                    )
                # Honest retry: возвращаем сохранённый `Payment` без побочных эффектов.
                return existing

        # Первая вставка.
        confirmed_at = occurred_at if status is PaymentStatus.CONFIRMED else None
        payment = Payment(
            player_id=player_id,
            currency=currency,
            amount_native=amount_native,
            idempotency_key=idempotency_key,
            status=status,
            created_at=occurred_at,
            provider_payment_id=provider_payment_id,
            confirmed_at=confirmed_at,
            payload=MappingProxyType(dict(payload))
            if payload is not None
            else MappingProxyType({}),
        )
        self.rows.append(payment)
        return payment

    async def get_by_idempotency_key(
        self,
        *,
        idempotency_key: IdempotencyKey,
    ) -> Payment | None:
        """Линейный поиск по `rows`."""
        for existing in self.rows:
            if existing.idempotency_key == idempotency_key:
                return existing
        return None
