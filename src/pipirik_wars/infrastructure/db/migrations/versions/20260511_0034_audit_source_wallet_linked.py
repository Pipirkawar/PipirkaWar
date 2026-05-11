"""Расширение whitelist ``audit_log.source`` источником ``wallet_linked`` (Спринт 4.1-D).

``AuditSource.WALLET_LINKED`` — привязка TON-кошелька игрока
(ГДД §12.6.4). Пишется use-case-ом ``LinkWallet``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_audit_source_wallet_linked"
down_revision: str | Sequence[str] | None = "0033_audit_source_prize_lot_claimed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
    "prize_pool_increment",
    "prize_lot_generated",
    "prize_lot_refunded",
    "prize_lot_reserved",
    "prize_lot_claimed",
    "wallet_linked",
    "unknown",
)

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
    "roulette_paid_reward",
    "prize_pool_increment",
    "prize_lot_generated",
    "prize_lot_refunded",
    "prize_lot_reserved",
    "prize_lot_claimed",
    "unknown",
)


def _check_clause(values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"source IN ({quoted})"


def upgrade() -> None:
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_SOURCE_WHITELIST),
        )
    _ = sa


def downgrade() -> None:
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_PREV_SOURCE_WHITELIST),
        )
