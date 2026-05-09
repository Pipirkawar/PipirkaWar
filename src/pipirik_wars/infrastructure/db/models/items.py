"""ORM-модель `items` — инвентарь игрока (Спринт 3.4-B).

Хранит **только** persistence-данные, общие для всех игроков:
- идентификатор каталожной записи (`item_id` ↔ `items_catalog`-id из
  `balance.yaml`);
- уровень заточки (`enchant_level: 0..30`, ГДД §2.8.2);
- момент получения предмета (`acquired_at` — для сортировки в UI
  инвентаря; задаётся при дропе из forest/mountain/dungeon/boss).

Каталог-связные поля (`slot`, `display_name`, `rarity`) **не
дублируются** в БД — они берутся из `balance.yaml/items_catalog`
по `item_id`. Один источник правды (ГДД §2.6 «каталог плоский»).
Денормализованная `category` тоже отсутствует — выводится из
`Slot` через `ItemCategory.from_slot(...)`.

Composite PK `(player_id, item_id)` — каждый каталожный предмет
существует в инвентаре игрока в единственном экземпляре (ГДД §2.6
«предмет либо надет, либо выброшен»; стэкаемые скроллы — отдельная
таблица 3.4-C).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base


class ItemORM(Base):
    """Строка таблицы `items`."""

    __tablename__ = "items"

    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_items_player_id_users"),
        nullable=False,
    )
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    enchant_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("player_id", "item_id", name="pk_items"),
        CheckConstraint(
            "enchant_level >= 0 AND enchant_level <= 30",
            name="ck_items_enchant_level_range",
        ),
    )
