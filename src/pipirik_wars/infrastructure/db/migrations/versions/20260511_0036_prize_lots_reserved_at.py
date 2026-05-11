"""Добавляет колонку ``reserved_at`` в ``prize_lots`` (Спринт 4.1-D, D.9.b).

В состоянии 4.1-C `prize_lots` хранила только `created_at` и
`claimed_at`. Refund-таймауту `RESERVED → REFUNDED` (D.9) нужно знать
**когда** лот был зарезервирован — иначе нельзя определить, истёк ли
TTL (D.9.a balance-config `prize_lot.reserved_ttl_seconds = 48h`).
Эта миграция добавляет `reserved_at TIMESTAMP WITH TIME ZONE NULL` +
covering composite-индекс `(status, reserved_at)` + CHECK-инвариант
консистентности с `status`.

Колонка nullable: ACTIVE-лот не имеет момента резервирования (NULL),
RESERVED-лот обязан иметь (домен и CHECK-constraint гарантируют),
CLAIMED / REFUNDED — любое значение (зависит от пути в state-machine).

* ACTIVE → RESERVED (D.5/C.6.c): репозиторий пишет
  `UPDATE ... SET reserved_at=:reserved_at WHERE status='active'`.
* RESERVED → CLAIMED (4.1-D D.7 `ClaimPrize`): `reserved_at` сохраняется
  (референс на момент брони — нужно для аудита).
* RESERVED → REFUNDED (D.9.c `ExpireReservedPrizeLots`): `reserved_at`
  сохраняется (нужно для аудита-`reason` = «timeout»).
* ACTIVE → REFUNDED (4.1-E `/refund_lot`): `reserved_at = NULL`.

Backward compat: существующие prod-строки 4.1-C получат `reserved_at =
NULL`. Это совместимо со всеми статусами кроме RESERVED, поэтому
поднимать миграцию надо, когда либо нет RESERVED-лотов, либо есть
сопровождающий backfill-скрипт. В рамках 4.1-D PR-а 4.1-C ещё не
влит в прод (мы внутри PR-цикла 4.1-D), так что backfill не нужен.

CHECK-инвариант ``ck_prize_lots_reserved_at_consistent`` — last-line-
of-defense; доменный invariant `PrizeLot.__post_init__` сторожит то
же самое ещё до записи.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_prize_lots_reserved_at"
down_revision: str | Sequence[str] | None = "0035_wallets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `batch_alter_table` нужен для SQLite (`ALTER TABLE ... ADD CONSTRAINT`
    # без него не работает); на Postgres-е batch — no-op.
    with op.batch_alter_table("prize_lots") as batch:
        batch.add_column(
            sa.Column(
                "reserved_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        batch.create_check_constraint(
            "ck_prize_lots_reserved_at_consistent",
            "(status = 'active' AND reserved_at IS NULL) "
            "OR (status = 'reserved' AND reserved_at IS NOT NULL) "
            "OR (status IN ('claimed', 'refunded'))",
        )
    op.create_index(
        "ix_prize_lots_status_reserved_at",
        "prize_lots",
        ["status", "reserved_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prize_lots_status_reserved_at",
        table_name="prize_lots",
    )
    with op.batch_alter_table("prize_lots") as batch:
        batch.drop_constraint(
            "ck_prize_lots_reserved_at_consistent",
            type_="check",
        )
        batch.drop_column("reserved_at")
