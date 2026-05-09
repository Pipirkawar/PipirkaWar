"""Scrolls persistence (Спринт 3.4-C, ГДД §2.8): создание таблицы `scrolls`.

Доменный слой 3.4-C ввёл порт `IScrollRepository` (Спринт 3.4-C, C.1) —
эта миграция создаёт таблицу `scrolls`, на которую опирается
`SqlAlchemyScrollRepository` и use-case `EnchantItem`.

Колонки:

* `player_id BIGINT NOT NULL` — FK → `users.id` (`ON DELETE CASCADE`).
* `scroll_id VARCHAR(64) NOT NULL` — стабильный string-id формата
  `{category.value}:{regular|blessed}` (см. `Scroll.scroll_id`-property
  в `domain/enchantment/entities.py`). Возможные значения (6 шт.):
  `weapon_scroll:regular`, `weapon_scroll:blessed`,
  `armor_scroll:regular`, `armor_scroll:blessed`,
  `jewelry_scroll:regular`, `jewelry_scroll:blessed`.
* `qty INTEGER NOT NULL` — счётчик стэка скроллов. Начальное
  значение задаётся `add(...)`-вызовом репо (всегда `>= 1`),
  декрементится `consume(qty)`-методом use-case-а `EnchantItem`.
* `acquired_at TIMESTAMP WITH TIME ZONE NOT NULL` — момент **первого**
  попадания этого `scroll_id` в инвентарь. На последующих `add(qty)`-ах
  не обновляется (для UI-сортировки достаточно «когда впервые получил»).

Composite PK `(player_id, scroll_id)` — у игрока ровно одна строка
на каждую (категория, blessed)-комбинацию (стэк). При `add(qty)`-е
с уже существующей записью репо инкрементит `qty`, а не создаёт
дубликат (UPSERT-семантика).

CHECK-инвариант:

* `qty >= 0` — last-line-of-defense на случай прямых SQL-правок.
  `consume(qty)` атомарно проверяет `qty >= requested` перед
  декрементом, и если случайно проскочит race-condition — CHECK
  не позволит уйти в отрицательные числа. Доменный слой обещает,
  что `qty=0`-строки могут существовать (после полного расходования
  стэка) — это нормальное состояние, отличаемое от «нет строки»
  (`ScrollNotFoundError` vs `ScrollOutOfStockError`).

Индексов помимо PK нет — все запросы идут по `(player_id, scroll_id)`
(точечный `get` / `update`-by-PK). Listing-инвентаря в bot-handler-е
3.4-D, тогда же добавим `ix_scrolls_player_acquired` отдельной
миграцией (правило ГДД-7: «не индексируем заранее»).

`audit_log_source_whitelist` миграция не расширяет — заточка
пишется через `ITEM_ENCHANT_ATTEMPT`/`ENCHANT_ANOMALY`-action
(добавляются в C.4), не через source-key.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022_scrolls"
down_revision: str | Sequence[str] | None = "0021_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scrolls",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("scroll_id", sa.String(length=64), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("player_id", "scroll_id", name="pk_scrolls"),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["users.id"],
            name="fk_scrolls_player_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "qty >= 0",
            name="ck_scrolls_qty_non_negative",
        ),
    )


def downgrade() -> None:
    op.drop_table("scrolls")
