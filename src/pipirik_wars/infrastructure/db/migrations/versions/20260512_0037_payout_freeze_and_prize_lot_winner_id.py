"""Persistence freeze-флага + winner_id на prize_lots (Спринт 4.1-E, E.11a).

Две связанные схемные изменения:

1. **Новая singleton-таблица ``payout_freeze``** — хранит глобальный
   freeze-флаг крипто-выплат (ГДД §12.6.5). Одна строка с ``id=1``
   (CHECK ``id = 1`` гарантирует уникальность сингла), seed-row
   создаётся в ``upgrade()`` с ``is_frozen=False``. Используется
   доменным агрегатом ``PayoutFreeze`` (E.4) через порт
   ``IPayoutFreezeRepository`` (E.4) — SQL-реализация в E.11a.

   Инварианты:

   * ``id = 1`` — singleton, доп-строки запрещены CHECK-ом.
   * ``is_frozen=TRUE`` ⇒ все три nullable-поля
     (``frozen_by_admin_id``, ``frozen_at``, ``reason``) заполнены.
   * ``is_frozen=FALSE`` ⇒ все три nullable-поля равны ``NULL``.

2. **Новая колонка ``prize_lots.winner_id BIGINT NULL``** + покрывающий
   composite-индекс ``(winner_id, currency, status, claimed_at)``.
   Колонка нужна для rolling-30d-payout-limit (E.6 ``EvaluatePayoutLimit``
   use-case + E.10 hook в ``ClaimPrize``); индекс покрывает
   ``SELECT SUM(amount_native) WHERE winner_id=? AND currency=? AND
   status='claimed' AND claimed_at >= ?`` index-only scan-ом на
   Postgres-е.

   ``winner_id`` записывается в одной транзакции с
   ``status='claimed'`` через расширенный ``IPrizeLotRepository.
   update_status(winner_id=...)`` в E.11a-update; до E.11a колонка
   всегда NULL, после — non-NULL для всех новых CLAIMED-лотов.
   Существующие CLAIMED-лоты (если есть) остаются с
   ``winner_id=NULL`` — это совместимо с CHECK-инвариантом ниже:

   * ``ck_prize_lots_winner_id_iff_claimed_or_null`` — лот в
     status ∈ ('active', 'reserved', 'refunded') ⇒ ``winner_id IS
     NULL``. Для status='claimed' допускаются ``winner_id IS NULL``
     (legacy 4.1-D) или ``winner_id > 0`` (новые claim-ы).

   Backward-compat: 4.1-D смержен в ``main``, но реальных claimed-лотов
   в проде ещё нет (фича только-только зашла, prize-пул только-только
   начали заполнять). Если бы они были — нужен был бы backfill-скрипт
   (источник winner_id — actor_id в audit-записи PRIZE_LOT_CLAIMED).

CHECK-инварианты — last-line-of-defense; доменные invariants
``PayoutFreeze.__post_init__`` и ``ClaimPrize.execute(...)`` сторожат
то же самое ещё до записи.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_payout_freeze_and_prize_lot_winner_id"
down_revision: str | Sequence[str] | None = "0036_prize_lots_reserved_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------- payout_freeze ---------------------------- #
    op.create_table(
        "payout_freeze",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "is_frozen",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("frozen_by_admin_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "frozen_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "id = 1",
            name="ck_payout_freeze_singleton",
        ),
        sa.CheckConstraint(
            "(is_frozen = 0 AND frozen_by_admin_id IS NULL "
            "AND frozen_at IS NULL AND reason IS NULL) "
            "OR (is_frozen = 1 AND frozen_by_admin_id IS NOT NULL "
            "AND frozen_at IS NOT NULL AND reason IS NOT NULL)",
            name="ck_payout_freeze_attrs_consistent",
        ),
        sa.CheckConstraint(
            "frozen_by_admin_id IS NULL OR frozen_by_admin_id > 0",
            name="ck_payout_freeze_admin_id_positive",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR LENGTH(reason) > 0",
            name="ck_payout_freeze_reason_non_empty",
        ),
    )

    # Seed единственной строки: id=1, is_frozen=FALSE — соответствует
    # `PayoutFreeze.unfrozen()`-фабричному default-у.
    op.execute(
        sa.text(
            "INSERT INTO payout_freeze (id, is_frozen, frozen_by_admin_id, "
            "frozen_at, reason) VALUES (1, FALSE, NULL, NULL, NULL)",
        ),
    )

    # ----------------- prize_lots.winner_id + покрывающий индекс ----------- #
    with op.batch_alter_table("prize_lots") as batch:
        batch.add_column(
            sa.Column(
                "winner_id",
                sa.BigInteger(),
                nullable=True,
            ),
        )
        batch.create_check_constraint(
            "ck_prize_lots_winner_id_iff_claimed_or_null",
            "(status = 'claimed') OR (winner_id IS NULL)",
        )
        batch.create_check_constraint(
            "ck_prize_lots_winner_id_positive",
            "winner_id IS NULL OR winner_id > 0",
        )
    op.create_index(
        "ix_prize_lots_winner_currency_status_claimed_at",
        "prize_lots",
        ["winner_id", "currency", "status", "claimed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prize_lots_winner_currency_status_claimed_at",
        table_name="prize_lots",
    )
    with op.batch_alter_table("prize_lots") as batch:
        batch.drop_constraint(
            "ck_prize_lots_winner_id_positive",
            type_="check",
        )
        batch.drop_constraint(
            "ck_prize_lots_winner_id_iff_claimed_or_null",
            type_="check",
        )
        batch.drop_column("winner_id")
    op.drop_table("payout_freeze")
