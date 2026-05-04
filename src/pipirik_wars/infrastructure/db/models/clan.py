"""ORM-модели `clans` и `clan_members` (Спринт 1.1)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base

_AutoIncBigInt = BigInteger().with_variant(Integer, "sqlite")


class ClanORM(Base):
    """Таблица `clans` (ГДД §1.4 — §1.5).

    `chat_id` Telegram'а в Postgres помещается в BigInteger (для
    супергрупп идёт `-100…`). Уникальность `chat_id` — DB-инвариант,
    use-case `RegisterClan` опирается на него (дубль = `IntegrityError`).

    `chat_kind` хранит `"group"` / `"supergroup"` (`domain.clan.ChatKind`).
    Меняется при миграции group → supergroup (см. `Clan.with_chat_id`).
    """

    __tablename__ = "clans"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    chat_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="active",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ClanMemberORM(Base):
    """Таблица `clan_members` (ГДД §4 «Кланы»).

    PK составной — `(clan_id, player_id)`: один и тот же игрок не может
    быть в одном клане дважды.

    Дополнительный `UniqueConstraint(player_id)` — DB-инвариант
    «один игрок = один клан за раз» (правило ГДД §4). Без него игрок
    мог бы дублироваться в нескольких кланах одновременно при гонке
    `JoinClan` от двух чатов сразу.

    `ON DELETE CASCADE` на обоих FK — членство автоматически удаляется,
    если удалили клан или игрока (в нашем случае «удаление» — это
    редкая операция чистки админом, не штатный путь).
    """

    __tablename__ = "clan_members"

    clan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clans.id", ondelete="CASCADE"),
        primary_key=True,
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="member",
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("player_id", name="uq_clan_members_player_id"),)
