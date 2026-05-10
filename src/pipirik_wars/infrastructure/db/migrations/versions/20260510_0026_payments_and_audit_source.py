"""Persistence платежей + audit-source `roulette_paid_reward` (Спринт 4.1-A, A.5).

Доменный слой 4.1-A (`domain.monetization.entities.Payment` + порт
`IPaymentLedger`) ввёл VO/сущности и контракт ledger-а без persistence.
Эта миграция создаёт таблицу `payments`, на которую опирается
`SqlAlchemyPaymentLedger` и use-case `SpinPaidRoulette`.

Колонки:

* `id BIGINT PK AUTOINCREMENT` — суррогатный ключ строки. В SQLite
  это `INTEGER PRIMARY KEY AUTOINCREMENT`, в Postgres — `BIGSERIAL`
  (через `with_variant` в ORM-модели).
* `player_id BIGINT NOT NULL` — FK → `users.id` (`ON DELETE CASCADE`).
* `currency VARCHAR(16) NOT NULL` — машинный id валюты
  (`Currency.value`: `stars` / `ton_nano` / `usdt_decimal`). Первичная
  CHECK-валидация в whitelist; домену стоит расширять и whitelist при
  добавлении новых валют (см. 4.1-D под TON/USDT).
* `amount_native NUMERIC(38, 0) NOT NULL` — сумма в минимальных
  единицах валюты (`Payment.amount_native`). NUMERIC(38,0) выбран,
  чтобы вместить `USDT_DECIMAL` (jetton-decimals=6, теоретически
  огромные суммы) без потери точности; для STARS/TON_NANO Postgres
  всё равно использует машинное представление.
* `idempotency_key VARCHAR(64) NOT NULL` — стабильный ключ
  дедупликации (валидирован `IdempotencyKey`-VO под regex
  `[A-Za-z0-9_\\-:]{1,64}`). Уникальность — на пару
  `(player_id, idempotency_key)`, чтобы разные игроки могли
  использовать одинаковые ключи (но один игрок — нет).
* `status VARCHAR(16) NOT NULL DEFAULT 'pending'` — статус платежа
  (`PaymentStatus.value`: `pending` / `confirmed` / `refunded`).
* `provider_payment_id VARCHAR(128) NULL` — id платежа на стороне
  провайдера (`successful_payment.telegram_payment_charge_id` для TG
  Stars; `tx_hash` для TON в 4.1-D). На моменте `PENDING` — `NULL`,
  проставляется при переходе в `CONFIRMED`.
* `payload JSON NOT NULL DEFAULT '{}'` — провайдер-специфичный
  payload (Postgres хранит как JSONB-совместимый JSON, SQLite — как
  TEXT-обёртку). Для TG Stars: `{"pack": "single", "n_spins": "1"}`,
  и т.п.
* `created_at TIMESTAMP WITH TIME ZONE NOT NULL` — момент создания
  записи (TZ-aware; доменный VO `Payment.__post_init__` отказывает
  naïve-datetime).
* `confirmed_at TIMESTAMP WITH TIME ZONE NULL` — момент перехода в
  `CONFIRMED` (TZ-aware). Для `PENDING`/`REFUNDED` без подтверждения
  — `NULL`.

Индексы:

* `uq_payments_player_id_idempotency_key UNIQUE(player_id,
  idempotency_key)` — гарантирует append-only-идемпотентность.
  Повторный `INSERT ... ON CONFLICT (player_id, idempotency_key) DO
  NOTHING` — no-op (см. `SqlAlchemyPaymentLedger.charge`).
* `ix_payments_idempotency_key (idempotency_key)` — для
  `get_by_idempotency_key(...)` без `player_id`. На 4.1-A use-case
  всегда вызывает `charge` (он сам идемпотентен), но в 4.1-D этот
  метод понадобится `successful_payment`-handler-у.

CHECK-инварианты (зеркалят доменные `__post_init__`-проверки):

* `ck_payments_currency_whitelist` — `currency IN ('stars',
  'ton_nano', 'usdt_decimal')`. Last-line-of-defense на случай
  прямых SQL-правок / ENUM-shift-багов.
* `ck_payments_status_whitelist` — `status IN ('pending', 'confirmed',
  'refunded')`. Аналогично.
* `ck_payments_amount_native_positive` — `amount_native >= 1`.
  Доменный VO `Payment.__post_init__` уже сторожит `amount_native >= 1`,
  но защита на уровне БД — last-line-of-defense.
* `ck_payments_confirmed_consistency` — `(status = 'confirmed' AND
  confirmed_at IS NOT NULL AND provider_payment_id IS NOT NULL) OR
  (status != 'confirmed')`. Зеркалит инвариант
  `Payment(status=CONFIRMED) requires confirmed_at + provider_payment_id`.
* `ck_payments_pending_no_confirmed_at` — `(status != 'pending') OR
  (confirmed_at IS NULL)`. Зеркалит инвариант `Payment(status=PENDING)
  must have confirmed_at=None`.

`audit_log.source` whitelist:

* `stars_payment` уже в whitelist (добавлен `0007_anticheat_foundation`).
  Новые DDL-правки под этот источник не нужны.
* **`roulette_paid_reward`** — эта миграция расширяет whitelist.
  Энам-значение `AuditSource.ROULETTE_PAID_REWARD` введено в
  спринте 4.1-A.A.3 в `domain/shared/ports/audit.py`, но DB-CHECK
  отставал. Use-case `SpinPaidRoulette.execute(...)` пишет
  `audit_log` со `source=roulette_paid_reward` (выдача length-награды
  за оплаченный спин §12.5.2). Без этого расширения финальный
  audit-INSERT в use-case-е падает на IntegrityError, и в unit-тесте
  `test_audit_source_whitelist_matches_db_check` виден дрифт enum-а вс.
  миграции. Парного `roulette_paid_cost`-source-а **нет**
  (cost-сторона — это запись в `payments`-таблицу, не в `audit_log`).

`anticheat.donate_sources` в `config/balance.yaml` уже содержит
`stars_payment` — дополнительных расширений не требуется.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026_payments_and_audit_source"
down_revision: str | Sequence[str] | None = "0025_audit_source_oracle_tribe_bonus"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Обновлённый whitelist `audit_log.source`. Должен совпадать с
# `pipirik_wars.domain.shared.ports.audit.AuditSource` — расхождение
# ловит unit-тест `test_audit_source_whitelist_matches_db_check`.
_SOURCE_WHITELIST: tuple[str, ...] = (
    "forest",
    "mountains",
    "dungeon",
    "oracle",
    "referral_signup",
    "referral_thickness",
    "pvp_reward",
    "caravan_reward",
    "raid_reward",
    "admin_grant",
    "admin_refund",
    "stars_payment",
    "ton_payment",
    "usdt_payment",
    "daily_head",
    "roulette_free_cost",
    "roulette_free_reward",
    "oracle_tribe_bonus",
    "roulette_paid_reward",
    "unknown",
)

# Whitelist до 4.1-A (для downgrade()).
_PREV_SOURCE_WHITELIST: tuple[str, ...] = (
    "forest",
    "mountains",
    "dungeon",
    "oracle",
    "referral_signup",
    "referral_thickness",
    "pvp_reward",
    "caravan_reward",
    "raid_reward",
    "admin_grant",
    "admin_refund",
    "stars_payment",
    "ton_payment",
    "usdt_payment",
    "daily_head",
    "roulette_free_cost",
    "roulette_free_reward",
    "oracle_tribe_bonus",
    "unknown",
)


def _check_clause(values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"source IN ({quoted})"


def upgrade() -> None:
    # 1) Расширение `audit_log_source_whitelist` для `roulette_paid_reward`.
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_SOURCE_WHITELIST),
        )

    # 2) Создание таблицы `payments`.
    op.create_table(
        "payments",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("amount_native", sa.Numeric(precision=38, scale=0), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=True),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["users.id"],
            name="fk_payments_player_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "player_id",
            "idempotency_key",
            name="uq_payments_player_id_idempotency_key",
        ),
        sa.CheckConstraint(
            "currency IN ('stars', 'ton_nano', 'usdt_decimal')",
            name="ck_payments_currency_whitelist",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'refunded')",
            name="ck_payments_status_whitelist",
        ),
        sa.CheckConstraint(
            "amount_native >= 1",
            name="ck_payments_amount_native_positive",
        ),
        sa.CheckConstraint(
            "(status = 'confirmed' AND confirmed_at IS NOT NULL "
            "AND provider_payment_id IS NOT NULL) "
            "OR (status != 'confirmed')",
            name="ck_payments_confirmed_consistency",
        ),
        sa.CheckConstraint(
            "(status != 'pending') OR (confirmed_at IS NULL)",
            name="ck_payments_pending_no_confirmed_at",
        ),
    )
    op.create_index(
        "ix_payments_idempotency_key",
        "payments",
        ["idempotency_key"],
    )


def downgrade() -> None:
    # 1) Снятие таблицы `payments`.
    op.drop_index(
        "ix_payments_idempotency_key",
        table_name="payments",
    )
    op.drop_table("payments")

    # 2) Откат `audit_log_source_whitelist` к пред-4.1-A набору.
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_PREV_SOURCE_WHITELIST),
        )
