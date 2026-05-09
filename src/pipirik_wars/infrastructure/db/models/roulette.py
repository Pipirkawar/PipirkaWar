"""ORM-модель `roulette_spins` — event-log free-to-play рулетки (Спринт 3.5-B).

Append-only таблица: каждая прокрутка `/roulette_free` (ГДД §12.4)
кладётся одной строкой; никаких UPDATE-ов. Источник правды для
будущих audit-выгрузок и для anti-cheat-проверки cooldown в use-case-е
`SpinFreeRoulette` (Спринт 3.5-C).

Колонки:

* `id BIGINT AUTOINCREMENT PRIMARY KEY` — суррогатный ключ строки.
  В SQLite — `INTEGER` (через `with_variant`), в Postgres — `BIGINT`.
* `player_id BIGINT NOT NULL` — FK → `users.id` (`ON DELETE CASCADE`).
* `occurred_at TIMESTAMP WITH TIME ZONE NOT NULL` — момент прокрутки
  (TZ-aware; доменный VO `RouletteSpin.__post_init__` отказывает
  naïve-datetime).
* `kind VARCHAR(32) NOT NULL` — машинный id типа исхода
  (`RouletteOutcomeKind.value`: `length` / `item` / `scroll_regular`
  / `scroll_blessed` / `crypto_lot`). Денормализован для быстрых
  фильтр-выгрузок «сколько раз выпал scroll_blessed за период».
* `length_cm INTEGER NULL` — выпавшее количество сантиметров (только
  при `kind = 'length'`; для остальных — `NULL`). DB-CHECK
  `ck_roulette_spins_length_cm_matches_kind` сторожит инвариант
  `kind ↔ length_cm` (зеркалит `RouletteOutcome.__post_init__`).
* `idempotency_key VARCHAR(128) NOT NULL UNIQUE` — стабильный ключ
  дедупликации (use-case 3.5-C сгенерит вид
  `f"roulette_free:{player_id}:{tg_message_id}"`). Уникальный индекс
  гарантирует append-only-идемпотентность: повторный
  `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING` — no-op.

Индексы:

* `(player_id, occurred_at DESC)` — для `last_free_spin_at(player_id)`
  одиночный `MAX(occurred_at) WHERE player_id = ?` идёт по индексу.
* Уникальный по `idempotency_key` (создаётся миграцией 0023 как
  `uq_roulette_spins_idempotency_key`).

CHECK-инварианты (зеркалят доменные `__post_init__`-проверки):

* `kind IN ('length', 'item', 'scroll_regular', 'scroll_blessed', 'crypto_lot')`
  — last-line-of-defense whitelist.
* `(kind = 'length' AND length_cm IS NOT NULL AND length_cm >= 1)
  OR (kind != 'length' AND length_cm IS NULL)` — DB-инвариант
  `kind ↔ length_cm`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base


class RouletteSpinORM(Base):
    """Строка таблицы `roulette_spins` — append-only event-log рулетки."""

    __tablename__ = "roulette_spins"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_roulette_spins_player_id_users",
        ),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    length_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_roulette_spins_idempotency_key",
        ),
        CheckConstraint(
            "kind IN ('length', 'item', 'scroll_regular', 'scroll_blessed', 'crypto_lot')",
            name="ck_roulette_spins_kind_whitelist",
        ),
        CheckConstraint(
            "(kind = 'length' AND length_cm IS NOT NULL AND length_cm >= 1)"
            " OR (kind != 'length' AND length_cm IS NULL)",
            name="ck_roulette_spins_length_cm_matches_kind",
        ),
        Index(
            "ix_roulette_spins_player_id_occurred_at",
            "player_id",
            "occurred_at",
        ),
    )
