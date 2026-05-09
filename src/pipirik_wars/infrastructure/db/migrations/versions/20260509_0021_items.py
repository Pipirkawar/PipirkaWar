"""Items persistence (Спринт 3.4-B, ГДД §2.6, §2.8): создание таблицы `items`.

Доменный слой 3.4-A (PR #117) ввёл агрегат `Item(id, category,
enchant_level)` и picker `pick_enchant_outcome` — но без persistence.
Эта миграция создаёт таблицу `items`, на которую опирается
`SqlAlchemyItemRepository` (3.4-B) и use-case `EnchantItem` (3.4-C).

Колонки:

* `player_id BIGINT NOT NULL` — FK → `users.id` (`ON DELETE CASCADE`).
* `item_id VARCHAR(64) NOT NULL` — каталожная ссылка
  (`item.<slot>.<short>`). Каталог живёт в `balance.yaml/items_catalog`,
  поэтому `slot` / `display_name` / `rarity` тут не дублируются.
  Категория (`weapon` / `armor` / `jewelry`) выводится из `Slot` в
  репо (`ItemCategory.from_slot(...)`), потому в БД её тоже нет.
* `enchant_level INTEGER NOT NULL DEFAULT 0` — уровень заточки
  (ГДД §2.8.2: лестница `0..30`). `server_default='0'` нужен, чтобы
  legacy-предметы (например, добавленные прямым `INSERT`-ом в обход
  ORM-а в будущих миграциях / админских скриптах) автоматически
  получали `+0`.
* `acquired_at TIMESTAMP WITH TIME ZONE NOT NULL` — когда предмет
  попал в инвентарь. Используется для сортировки в UI (3.4-D).

Composite PK `(player_id, item_id)` — каждый каталожный предмет
существует у игрока в единственном экземпляре (ГДД §2.6 «не копится:
надеть или выбросить»). Стэкаемые скроллы — отдельная таблица
`scrolls` в Спринте 3.4-C (вместе с use-case-ом `EnchantItem`).

CHECK-инвариант:

* `enchant_level >= 0 AND enchant_level <= 30` — last-line-of-defense
  на случай прямых SQL-правок в обход доменного слоя
  (`MAX_ENCHANT_LEVEL=30` хардкод в `domain/inventory/entities.py`).

Индексов помимо PK нет — все запросы 3.4-B / 3.4-C идут по
`(player_id, item_id)` (точечный `get` / `update`-by-PK), а
listing-инвентаря `WHERE player_id=:p ORDER BY acquired_at DESC` —
3.4-D, тогда же добавим `ix_items_player_acquired` отдельной
миграцией (правило ГДД-7: «не индексируем заранее под несуществующие
запросы»).

`audit_log_source_whitelist` миграция не расширяет — заточка
пишется через `ITEM_ENCHANT_ATTEMPT`-action (3.4-C), не через
source-key.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021_items"
down_revision: str | Sequence[str] | None = "0020_boss_fights"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column(
            "enchant_level",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("player_id", "item_id", name="pk_items"),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["users.id"],
            name="fk_items_player_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "enchant_level >= 0 AND enchant_level <= 30",
            name="ck_items_enchant_level_range",
        ),
    )


def downgrade() -> None:
    op.drop_table("items")
