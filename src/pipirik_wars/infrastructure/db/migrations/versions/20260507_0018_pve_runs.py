"""PvE-runs persistence (Спринт 3.1-B): mountain_runs + dungeon_runs + audit-whitelist.

Доменный слой 3.1-A добавил `domain/{mountains,dungeon}/` (Спринт 3.1-A,
PR #99). Этот PR (3.1-B) приземляет персистентность:

1. **Расширение `audit_log_source_whitelist`** — добавляем `mountains` и
   `dungeon` в whitelist `audit_log.source` (см. модель
   `pipirik_wars.infrastructure.db.models.security.AuditLogORM`,
   первоначально создан в миграции 0007, затем расширен в 0014).

2. **`mountain_runs`** — таблица походов в горы (ГДД §8). Структура
   зеркалит `forest_runs` с двумя отличиями:
   * `length_delta_cm` — **знаковая** (gain → ≥ 0, loss → ≤ 0); без
     `>= 0`-CHECK-а.
   * `drops` — `JSON`-массив `[{"item_id": "..."}]`, длиной 0..max_drops.
     Имена в горах не дропаются (ГДД §2.5), скроллы пока — Спринт 3.1-D.
   * Знак ветки (`gain`/`loss`) хранится отдельной колонкой `branch_sign`
     для DB-CHECK-а «знак согласован со знаком дельты». На уровне
     domain-сущности (`MountainRun`) эта колонка избыточна — repo при
     deserialize-е её игнорирует, а при INSERT-е выводит из
     `length_delta_cm`.

3. **`dungeon_runs`** — полностью идентичная mountain_runs таблица для
   данжона (ГДД §8). Отличается лишь именами constraint-ов и индексов.

CHECK-инварианты (зеркалят forest_runs + загартируют ±-семантику):
* `status IN ('in_progress', 'finished')`
* `branch_sign IN ('gain', 'loss')`
* `(branch_sign='gain' AND length_delta_cm>=0) OR (branch_sign='loss' AND length_delta_cm<=0)`
* `(status='in_progress' AND finished_at IS NULL) OR (status='finished' AND finished_at IS NOT NULL)`
* `ends_at > started_at`

Индексы:
* `(player_id, status)` — preflight `StartMountainRun` / `StartDungeonRun`.
* `(status, ends_at)` — recovery-сканирование готовых к финишу запусков.
* Частичный уникальный `(player_id) WHERE status='in_progress'` —
  жёсткий БД-инвариант «у игрока не более одного активного похода
  в каждой локации» (на одном уровне с activity_lock).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_pve_runs"
down_revision: str | Sequence[str] | None = "0017_admins_totp_secret"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Обновлённый whitelist `audit_log.source`. Должен совпадать с
# `pipirik_wars.domain.shared.ports.audit.AuditSource` — расхождение
# ловит unit-тест `test_audit_source_whitelist_matches_db_check`.
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
    "unknown",
)

# Whitelist до 3.1-B (для downgrade()).
_PREV_SOURCE_WHITELIST: tuple[str, ...] = (
    "forest",
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
    "unknown",
)


def _check_clause(values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"source IN ({quoted})"


def _create_pve_runs_table(table_name: str) -> None:
    """Создать `mountain_runs` или `dungeon_runs` (зеркальные структуры)."""
    op.create_table(
        table_name,
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("branch_name", sa.String(length=32), nullable=False),
        sa.Column("branch_sign", sa.String(length=8), nullable=False),
        sa.Column("length_delta_cm", sa.Integer(), nullable=False),
        sa.Column("drops", sa.JSON(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=f"pk_{table_name}"),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["users.id"],
            name=f"fk_{table_name}_player_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('in_progress', 'finished')",
            name=f"ck_{table_name}_status_valid",
        ),
        sa.CheckConstraint(
            "branch_sign IN ('gain', 'loss')",
            name=f"ck_{table_name}_branch_sign_valid",
        ),
        sa.CheckConstraint(
            # ±-инвариант: знак ветки согласован со знаком дельты.
            "(branch_sign = 'gain' AND length_delta_cm >= 0)"
            " OR (branch_sign = 'loss' AND length_delta_cm <= 0)",
            name=f"ck_{table_name}_sign_matches_delta",
        ),
        sa.CheckConstraint(
            # IN_PROGRESS-поход не имеет finished_at; FINISHED — обязан.
            "(status = 'in_progress' AND finished_at IS NULL)"
            " OR (status = 'finished' AND finished_at IS NOT NULL)",
            name=f"ck_{table_name}_finished_at_matches_status",
        ),
        sa.CheckConstraint(
            "ends_at > started_at",
            name=f"ck_{table_name}_ends_after_start",
        ),
    )
    op.create_index(
        f"ix_{table_name}_player_id_status",
        table_name,
        ["player_id", "status"],
    )
    op.create_index(
        f"ix_{table_name}_status_ends_at",
        table_name,
        ["status", "ends_at"],
    )
    op.create_index(
        f"uq_{table_name}_one_active_per_player",
        table_name,
        ["player_id"],
        unique=True,
        sqlite_where=sa.text("status = 'in_progress'"),
        postgresql_where=sa.text("status = 'in_progress'"),
    )


def _drop_pve_runs_table(table_name: str) -> None:
    op.drop_index(
        f"uq_{table_name}_one_active_per_player",
        table_name=table_name,
    )
    op.drop_index(f"ix_{table_name}_status_ends_at", table_name=table_name)
    op.drop_index(f"ix_{table_name}_player_id_status", table_name=table_name)
    op.drop_table(table_name)


def upgrade() -> None:
    # 1) Расширяем whitelist `audit_log.source`.
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_SOURCE_WHITELIST),
        )
    # 2) Таблицы PvE-походов.
    _create_pve_runs_table("mountain_runs")
    _create_pve_runs_table("dungeon_runs")


def downgrade() -> None:
    _drop_pve_runs_table("dungeon_runs")
    _drop_pve_runs_table("mountain_runs")
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_PREV_SOURCE_WHITELIST),
        )
