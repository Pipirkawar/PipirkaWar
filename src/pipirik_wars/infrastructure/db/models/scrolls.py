"""ORM-модель `scrolls` — стэкабельные скроллы заточки (Спринт 3.4-C).

В отличие от `items` (composite-PK `(player_id, item_id)` без `qty` —
один каталожный предмет в одном экземпляре, ГДД §2.6), скроллы
**стэкаются** в инвентаре игрока: одна строка
`(player_id, scroll_id)` хранит счётчик `qty INT`, инкрементящийся
дропами и декрементящийся `EnchantItem`-use-case-ом.

`scroll_id` — стабильный string-id `{category.value}:{regular|blessed}`
(см. `Scroll.scroll_id`-property в `domain/enchantment/entities.py`).
6 возможных значений — composite-PK `(player_id, scroll_id)` гарантирует
ровно одну строку на каждую (категория, blessed)-комбинацию у игрока.

Композиция полей соответствует `IScrollRepository` (Спринт 3.4-C):
- `get(player_id, scroll_id)` — точечное чтение по PK;
- `add(player_id, scroll_id, qty, now)` — UPSERT с `qty += :n`;
- `consume(player_id, scroll_id, qty=1)` — атомарный декремент с CHECK
  `qty - :n >= 0` (CHECK-инвариант на колонке + `WHERE qty >= :n` в
  репо — двойной защитник).

CHECK-инвариант `qty >= 0` — last-line-of-defense на случай прямых
SQL-правок (decrement не должен уйти ниже нуля). Доменный слой
обещает `qty > 0` после `add(...)`, репо — атомарно проверяет
`qty >= requested` перед `consume(...)`.

Индексов помимо PK нет (3.4-D добавит `ix_scrolls_player_acquired`,
если потребуется listing).
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
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base


class ScrollORM(Base):
    """Строка таблицы `scrolls` (стэкабельный скролл заточки)."""

    __tablename__ = "scrolls"

    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_scrolls_player_id_users"),
        nullable=False,
    )
    scroll_id: Mapped[str] = mapped_column(String(64), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("player_id", "scroll_id", name="pk_scrolls"),
        CheckConstraint("qty >= 0", name="ck_scrolls_qty_non_negative"),
    )
