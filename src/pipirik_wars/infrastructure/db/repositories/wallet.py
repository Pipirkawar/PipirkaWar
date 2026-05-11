"""Реализация ``IWalletRepository`` поверх таблицы ``wallets`` (Спринт 4.1-D, D.4).

Контракт порта — см. ``pipirik_wars.domain.monetization.ports.IWalletRepository``.
Подходы:

* ``add_or_replace(wallet)`` — INSERT с `ON CONFLICT (player_id,
  currency) DO UPDATE SET address, linked_at` для портабельного upsert
  (Postgres-native; для aiosqlite SQLAlchemy транслирует в
  `INSERT ... ON CONFLICT ... DO UPDATE`). После upsert возвращаем
  доменный ``Wallet``.
* ``get_by_player_and_currency(player_id, currency)`` — точечный SELECT
  по составному PK.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from pipirik_wars.domain.monetization.entities import Wallet
from pipirik_wars.domain.monetization.ports import IWalletRepository
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.infrastructure.db.models import WalletORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


def _ensure_utc(dt: datetime) -> datetime:
    """Нормализовать naïve-datetime как UTC (SQLite quirk: не хранит TZ-инфу)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class SqlAlchemyWalletRepository(IWalletRepository):
    """SQLAlchemy-реализация ``IWalletRepository`` поверх ``wallets``."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        """DI-конструктор.

        Args:
            uow: Unit-of-Work, поверх которого репозиторий работает.
                Caller обязан открыть `async with uow:` перед вызовами.
        """
        self._uow = uow

    async def add_or_replace(self, *, wallet: Wallet) -> Wallet:
        """Upsert ``wallet`` по составному PK ``(player_id, currency)``."""
        session = self._uow.session

        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "sqlite":
            sqlite_stmt = sqlite_insert(WalletORM).values(
                player_id=wallet.player_id,
                currency=wallet.currency.value,
                address=wallet.address,
                linked_at=wallet.linked_at,
            )
            sqlite_stmt = sqlite_stmt.on_conflict_do_update(
                index_elements=["player_id", "currency"],
                set_={
                    "address": sqlite_stmt.excluded.address,
                    "linked_at": sqlite_stmt.excluded.linked_at,
                },
            )
            await session.execute(sqlite_stmt)
        else:
            pg_stmt = pg_insert(WalletORM).values(
                player_id=wallet.player_id,
                currency=wallet.currency.value,
                address=wallet.address,
                linked_at=wallet.linked_at,
            )
            pg_stmt = pg_stmt.on_conflict_do_update(
                index_elements=["player_id", "currency"],
                set_={
                    "address": pg_stmt.excluded.address,
                    "linked_at": pg_stmt.excluded.linked_at,
                },
            )
            await session.execute(pg_stmt)
        return wallet

    async def get_by_player_and_currency(
        self,
        *,
        player_id: int,
        currency: Currency,
    ) -> Wallet | None:
        """Получить ``Wallet`` по составному ключу или ``None``."""
        session = self._uow.session
        stmt = select(WalletORM).where(
            WalletORM.player_id == player_id,
            WalletORM.currency == currency.value,
        )
        result = await session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return Wallet(
            player_id=orm.player_id,
            address=orm.address,
            currency=Currency(orm.currency),
            linked_at=_ensure_utc(orm.linked_at),
        )
