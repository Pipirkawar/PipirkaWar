"""Roulette spins persistence (Спринт 3.5-B, ГДД §12.4): таблица `roulette_spins`.

Доменный слой 3.5-A (PR #121) ввёл `RouletteOutcome` + чистую функцию
`pick_roulette_outcome` без persistence. Эта миграция создаёт
append-only event-log таблицу `roulette_spins`, на которую опирается
`SqlAlchemyRouletteSpinRepository` (3.5-B) и use-case `SpinFreeRoulette`
(3.5-C).

Колонки:

* `id BIGINT PK AUTOINCREMENT` — суррогатный ключ строки. В SQLite
  это `INTEGER PRIMARY KEY AUTOINCREMENT`, в Postgres — `BIGSERIAL`
  (через `with_variant` в ORM-модели).
* `player_id BIGINT NOT NULL` — FK → `users.id` (`ON DELETE CASCADE`).
* `occurred_at TIMESTAMP WITH TIME ZONE NOT NULL` — момент прокрутки.
  Доменный VO `RouletteSpin.__post_init__` отказывает naïve-datetime,
  так что в БД всегда лежит TZ-aware момент.
* `kind VARCHAR(32) NOT NULL` — машинный id типа исхода
  (`RouletteOutcomeKind.value`: `length` / `item` / `scroll_regular`
  / `scroll_blessed` / `crypto_lot`). Денормализован для быстрых
  audit-выгрузок «сколько раз выпал scroll_blessed за период».
* `length_cm INTEGER NULL` — выпавшее количество сантиметров (только
  при `kind = 'length'`; для остальных — `NULL`).
* `idempotency_key VARCHAR(128) NOT NULL` — стабильный ключ
  дедупликации (use-case 3.5-C сгенерит вид
  `f"roulette_free:{player_id}:{tg_message_id}"`).

Индексы:

* `uq_roulette_spins_idempotency_key UNIQUE(idempotency_key)` —
  гарантирует append-only-идемпотентность: повторный
  `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING` — no-op.
* `ix_roulette_spins_player_id_occurred_at (player_id, occurred_at)` —
  для быстрого `SELECT MAX(occurred_at) WHERE player_id = ?`
  (`last_free_spin_at`-метод репо). Ordering ASC/DESC не указываем
  явно — Postgres/SQLite одинаково умеют идти по B-tree-индексу
  в обе стороны для `MAX()`-агрегата.

CHECK-инварианты (зеркалят доменные `__post_init__`-проверки):

* `ck_roulette_spins_kind_whitelist` —
  `kind IN ('length', 'item', 'scroll_regular', 'scroll_blessed',
  'crypto_lot')`. Last-line-of-defense на случай прямых SQL-правок
  / ENUM-shift-багов. По мере добавления новых исходов в
  `RouletteOutcomeKind` список придётся обновить (но это редкое
  событие — за время игры состав исходов меняется на уровне
  весов, не на уровне состава типов).
* `ck_roulette_spins_length_cm_matches_kind` —
  `(kind = 'length' AND length_cm IS NOT NULL AND length_cm >= 1)
  OR (kind != 'length' AND length_cm IS NULL)`. DB-инвариант
  `kind ↔ length_cm` зеркалит `RouletteOutcome.__post_init__`:
  только для `kind=length` есть число сантиметров, для остальных
  типов — `NULL`.

`audit_log_source_whitelist` миграция не расширяет — рулетка пишется
в свой собственный event-log и в `audit_log` через action
`ROULETTE_FREE_SPIN` (добавится в 3.5-C), не через source-key.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023_roulette_spins"
down_revision: str | Sequence[str] | None = "0022_scrolls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roulette_spins",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("length_cm", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["users.id"],
            name="fk_roulette_spins_player_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_roulette_spins_idempotency_key",
        ),
        sa.CheckConstraint(
            "kind IN ('length', 'item', 'scroll_regular', 'scroll_blessed', 'crypto_lot')",
            name="ck_roulette_spins_kind_whitelist",
        ),
        sa.CheckConstraint(
            "(kind = 'length' AND length_cm IS NOT NULL AND length_cm >= 1)"
            " OR (kind != 'length' AND length_cm IS NULL)",
            name="ck_roulette_spins_length_cm_matches_kind",
        ),
    )
    op.create_index(
        "ix_roulette_spins_player_id_occurred_at",
        "roulette_spins",
        ["player_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_roulette_spins_player_id_occurred_at",
        table_name="roulette_spins",
    )
    op.drop_table("roulette_spins")
