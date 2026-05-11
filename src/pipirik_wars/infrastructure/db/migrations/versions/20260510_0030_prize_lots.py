"""Persistence лотов крипто-приза — таблица `prize_lots` (Спринт 4.1-C, C.3).

Доменный слой 4.1-C (C.1: `domain.monetization.entities.PrizeLot`
аггрегат + `PrizeLotStatus` enum + порт `IPrizeLotRepository`) и
application-слой (C.2: use-case `GeneratePrizeLots`, нарезающий
свободный остаток `PrizePool` на лоты с учётом `IFeeEstimator`)
работают пока поверх in-memory fake-репозитория. Эта миграция
создаёт таблицу `prize_lots`, на которую опирается
`SqlAlchemyPrizeLotRepository` (C.3) и интеграция picker-а
крипто-приза + резервирование в `SpinPaidRoulette`-flow (C.5–C.6).

Схема: **одна строка на каждый сгенерированный лот**. Размер лота
фиксирован моментом нарезки; статус мигрирует по машине состояний
`ACTIVE → RESERVED → CLAIMED|REFUNDED` (`PrizeLotStatus`). Идентификация
строки — суррогатный `id BIGSERIAL`.

Колонки:

* `id BIGINT PK AUTOINCREMENT` — суррогатный ключ (`BIGSERIAL` в
  Postgres, `INTEGER PRIMARY KEY AUTOINCREMENT` в SQLite через
  `with_variant` в ORM-модели). Совпадает с doмен-полем
  `PrizeLot.id: int | None` — `None` до `add(...)`, `int > 0` после.
* `currency VARCHAR(16) NOT NULL` — машинный id валюты
  (`Currency.value`: `stars` / `ton_nano` / `usdt_decimal`). CHECK-
  whitelist совпадает с `payments.currency` / `prize_pool_balance.currency`.
* `amount_native NUMERIC(38, 0) NOT NULL` — полный размер лота
  в минимальных единицах валюты (`>= 1`, CHECK на БД). Соответствует
  domain-полю `PrizeLot.amount_native`. NUMERIC(38,0) — тот же тип, что
  в `prize_pool_balance.balance_native` (jetton-decimals=6 +
  потенциально огромные суммы USDT).
* `fee_buffer_native NUMERIC(38, 0) NOT NULL` — заложенный буфер на
  оплату сетевой комиссии (`>= 0`, CHECK на БД). Соответствует
  `PrizeLot.fee_buffer_native: FeeBufferAmount`.
* `status VARCHAR(16) NOT NULL` — машинный id статуса
  (`PrizeLotStatus.value`: `active` / `reserved` / `claimed` /
  `refunded`). CHECK-whitelist last-line-of-defense.
* `created_at TIMESTAMP WITH TIME ZONE NOT NULL` — момент `add(...)`
  (TZ-aware).
* `claimed_at TIMESTAMP WITH TIME ZONE NULL` — момент `ClaimPrize`
  (TZ-aware). `NULL` для `ACTIVE` / `RESERVED` / `REFUNDED`, обязан
  быть выставлен для `CLAIMED` (CHECK ниже).

Инварианты (CHECK-constraints — last-line-of-defense, доменные
invariants сторожатся в `PrizeLot.__post_init__`):

* `ck_prize_lots_currency_whitelist` —
  `currency IN ('stars', 'ton_nano', 'usdt_decimal')`.
* `ck_prize_lots_amount_native_positive` — `amount_native >= 1`.
  Зеркалит invariant `PrizeLotInvariantError`-ветки в домене.
* `ck_prize_lots_fee_buffer_non_negative` — `fee_buffer_native >= 0`.
  Зеркалит invariant VO `FeeBufferAmount`.
* `ck_prize_lots_amount_greater_than_fee_buffer` —
  `amount_native > fee_buffer_native`. Гарантирует, что после
  удержания комиссии игроку остаётся хотя бы `1` минимальная единица.
* `ck_prize_lots_status_whitelist` —
  `status IN ('active', 'reserved', 'claimed', 'refunded')`.
* `ck_prize_lots_claimed_at_iff_claimed` —
  `(status = 'claimed' AND claimed_at IS NOT NULL) OR
   (status <> 'claimed' AND claimed_at IS NULL)`. Зеркалит invariant
  «`CLAIMED ⇔ claimed_at`» из `PrizeLot.__post_init__`.

Индексы:

* `ix_prize_lots_status_currency` — `(status, currency)`. Покрывает
  `list_active(currency)` запрос picker-а (`WHERE status='active' AND
  currency=:c`). Compound-индекс с `status` первой колонкой
  оптимизирует фильтрацию по самому селективному параметру (статусов
  4, валют 3 — порядок неважен на маленькой таблице, но при росте
  лотов до 10^5+ выигрыш будет; см. ГДД §12.6.3 — лоты могут
  накапливаться, если рулетка простаивает).

В отличие от `0027_prize_pool_balance`, тут **нет initial-seed-а**:
лоты появляются динамически через `GeneratePrizeLots.execute(...)`.

Audit-source `prize_lot_generated` уже расширен в `0029` (см.
комментарий там); этой миграцией whitelist не расширяется.

`prize_lot_refunded` source будет добавлен отдельной миграцией
`0031_audit_source_prize_lot_refunded` (шаг C.4) — нужен для будущего
refund-flow (`actual_fee > fee_buffer` в `ClaimPrize` 4.1-D или
admin-команда `/refund_lot` 4.1-E).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0030_prize_lots"
down_revision: str | Sequence[str] | None = "0029_audit_source_prize_lot_generated"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prize_lots",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column(
            "amount_native",
            sa.Numeric(precision=38, scale=0),
            nullable=False,
        ),
        sa.Column(
            "fee_buffer_native",
            sa.Numeric(precision=38, scale=0),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "claimed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "currency IN ('stars', 'ton_nano', 'usdt_decimal')",
            name="ck_prize_lots_currency_whitelist",
        ),
        sa.CheckConstraint(
            "amount_native >= 1",
            name="ck_prize_lots_amount_native_positive",
        ),
        sa.CheckConstraint(
            "fee_buffer_native >= 0",
            name="ck_prize_lots_fee_buffer_non_negative",
        ),
        sa.CheckConstraint(
            "amount_native > fee_buffer_native",
            name="ck_prize_lots_amount_greater_than_fee_buffer",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'reserved', 'claimed', 'refunded')",
            name="ck_prize_lots_status_whitelist",
        ),
        sa.CheckConstraint(
            "(status = 'claimed' AND claimed_at IS NOT NULL) "
            "OR (status <> 'claimed' AND claimed_at IS NULL)",
            name="ck_prize_lots_claimed_at_iff_claimed",
        ),
    )

    op.create_index(
        "ix_prize_lots_status_currency",
        "prize_lots",
        ["status", "currency"],
    )


def downgrade() -> None:
    op.drop_index("ix_prize_lots_status_currency", table_name="prize_lots")
    op.drop_table("prize_lots")
