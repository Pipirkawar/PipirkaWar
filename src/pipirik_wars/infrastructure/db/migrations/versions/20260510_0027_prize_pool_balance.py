"""Persistence призового пула — таблица `prize_pool_balance` (Спринт 4.1-B, B.3).

Доменный слой 4.1-B (`domain.monetization.entities.PrizePool` + порт
`IPrizePoolRepository`, шаги B.1–B.2) ввёл агрегат пула + use-case
`RecordDonation` (10% от подтверждённого платежа → пул) без persistence.
Эта миграция создаёт таблицу `prize_pool_balance`, на которую опирается
`SqlAlchemyPrizePoolRepository` (B.3) и use-case `RecordDonation` (B.5
интеграция в `SpinPaidRoulette`-flow).

Схема: **по одной строке на валюту** (`stars` / `ton_nano` / `usdt_decimal`),
а не одна строка с 3 колонками — это даёт:

* Атомарный per-currency `UPDATE ... WHERE currency = :c` + неявный row-lock
  в Postgres (concurrent writers по разным валютам не блокируют друг друга).
* Currency-isolation на уровне строки (`UNIQUE(currency)` исключает
  возможность дублей).
* Минимальный DDL-cost при добавлении 4-й валюты в будущем (только seed-row,
  схема не меняется).

Колонки:

* `id BIGINT PK AUTOINCREMENT` — суррогатный ключ строки (`BIGSERIAL` в
  Postgres, `INTEGER PRIMARY KEY AUTOINCREMENT` в SQLite через
  `with_variant` в ORM-модели).
* `currency VARCHAR(16) NOT NULL UNIQUE` — машинный id валюты
  (`Currency.value`: `stars` / `ton_nano` / `usdt_decimal`). CHECK-whitelist
  совпадает с `payments.currency` (см. миграцию `0026`). UNIQUE-constraint
  гарантирует ровно одну строку на валюту.
* `balance_native NUMERIC(38, 0) NOT NULL DEFAULT 0` — текущий баланс пула
  в native-юнитах валюты (`StarsPoolBalance.value` / `TonNanoAmount.value`
  / `UsdtDecimalAmount.value`). NUMERIC(38,0) — тот же тип, что в
  `payments.amount_native` (jetton-decimals=6 + потенциально огромные
  суммы USDT).
* `updated_at TIMESTAMP WITH TIME ZONE NOT NULL` — момент последнего
  `apply_increment(...)` (TZ-aware). На initial-seed = `NOW()`.

Инварианты:

* `ck_prize_pool_balance_currency_whitelist` — `currency IN ('stars',
  'ton_nano', 'usdt_decimal')`. Last-line-of-defense.
* `ck_prize_pool_balance_balance_native_non_negative` — `balance_native >= 0`.
  Зеркалит инвариант доменных VO `StarsPoolBalance` / `TonNanoAmount` /
  `UsdtDecimalAmount`.

Initial-seed: одна строка на каждую валюту с `balance_native = 0`.
Это гарантирует, что `apply_increment(...)` в репозитории (`UPDATE ...
WHERE currency = :c`) всегда находит существующую строку и атомарно её
обновляет — без UPSERT-ветки.

Audit-source `prize_pool_increment`:

* В этой миграции `audit_log_source_whitelist` **не** расширяется.
  Расширение перенесено в B.4 (отдельная миграция 0028) — там же
  добавится audit-запись внутри `RecordDonation.execute(...)` и
  enum-значение `AuditSource.PRIZE_POOL_INCREMENT`. Это разделение
  упрощает review (одна забота на коммит).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027_prize_pool_balance"
down_revision: str | Sequence[str] | None = "0026_payments_and_audit_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CURRENCY_VALUES: tuple[str, ...] = ("stars", "ton_nano", "usdt_decimal")


def upgrade() -> None:
    op.create_table(
        "prize_pool_balance",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column(
            "balance_native",
            sa.Numeric(precision=38, scale=0),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.UniqueConstraint("currency", name="uq_prize_pool_balance_currency"),
        sa.CheckConstraint(
            "currency IN ('stars', 'ton_nano', 'usdt_decimal')",
            name="ck_prize_pool_balance_currency_whitelist",
        ),
        sa.CheckConstraint(
            "balance_native >= 0",
            name="ck_prize_pool_balance_balance_native_non_negative",
        ),
    )

    # Initial seed — по одной row на каждую валюту с `balance_native = 0`.
    # Это гарантирует, что `apply_increment(...)` всегда находит существующую
    # строку без UPSERT-логики.
    seed_table = sa.table(
        "prize_pool_balance",
        sa.column("currency", sa.String()),
        sa.column("balance_native", sa.Numeric(precision=38, scale=0)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    seed_at = datetime(2026, 5, 10, 0, 0, tzinfo=UTC)
    op.bulk_insert(
        seed_table,
        [
            {
                "currency": currency,
                "balance_native": 0,
                "updated_at": seed_at,
            }
            for currency in _CURRENCY_VALUES
        ],
    )


def downgrade() -> None:
    op.drop_table("prize_pool_balance")
