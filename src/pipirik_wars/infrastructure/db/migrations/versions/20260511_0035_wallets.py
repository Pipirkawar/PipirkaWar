"""Persistence привязанных кошельков — таблица ``wallets`` (Спринт 4.1-D, D.4).

Один игрок может привязать по одному кошельку на каждую `Currency`
(`TON_NANO` / `USDT_DECIMAL`). PK составной — `(player_id, currency)`.
Идемпотентность `LinkWallet`: повторный INSERT того же `(player_id,
currency)` падает на PK; use-case заранее делает upsert через
`add_or_replace(...)`.

Колонки:

* ``player_id BIGINT NOT NULL`` — id игрока (часть PK).
* ``currency VARCHAR(16) NOT NULL`` — `Currency.value` (`ton_nano`
  или `usdt_decimal`; `stars` исключён — у Stars нет кошелька).
* ``address VARCHAR(96) NOT NULL`` — TON-адрес кошелька (raw
  `0:<64hex>` или user-friendly base64url 48 char). Длина 96 с
  запасом для будущих форматов.
* ``linked_at TIMESTAMP WITH TIME ZONE NOT NULL`` — момент привязки
  (TZ-aware).

Инварианты (CHECK):

* ``ck_wallets_currency_whitelist`` — `currency IN ('ton_nano',
  'usdt_decimal')`. STARS запрещён — у Stars нет кошелька.
* ``ck_wallets_address_non_empty`` — `LENGTH(address) > 0`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_wallets"
down_revision: str | Sequence[str] | None = "0034_audit_source_wallet_linked"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wallets",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("address", sa.String(length=96), nullable=False),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "player_id",
            "currency",
            name="pk_wallets",
        ),
        sa.CheckConstraint(
            "currency IN ('ton_nano', 'usdt_decimal')",
            name="ck_wallets_currency_whitelist",
        ),
        sa.CheckConstraint(
            "LENGTH(address) > 0",
            name="ck_wallets_address_non_empty",
        ),
    )


def downgrade() -> None:
    op.drop_table("wallets")
