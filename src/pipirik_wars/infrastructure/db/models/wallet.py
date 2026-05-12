"""ORM-модель ``wallets`` — привязанные TON/USDT-кошельки (Спринт 4.1-D, D.4).

Одна строка на пару `(player_id, currency)` (составной PK). Жизненный
цикл — `LinkWallet` upsert через ``SqlAlchemyWalletRepository.add_or_replace``.

Схема — см. миграцию ``0035_wallets``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base


class WalletORM(Base):
    """Строка таблицы ``wallets`` — один привязанный кошелёк."""

    __tablename__ = "wallets"

    player_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    currency: Mapped[str] = mapped_column(String(16), primary_key=True)
    address: Mapped[str] = mapped_column(String(96), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "currency IN ('ton_nano', 'usdt_decimal')",
            name="ck_wallets_currency_whitelist",
        ),
        CheckConstraint(
            "LENGTH(address) > 0",
            name="ck_wallets_address_non_empty",
        ),
    )
