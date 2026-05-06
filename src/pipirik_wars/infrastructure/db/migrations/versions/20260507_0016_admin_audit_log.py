"""Admin audit log table (Sprint 2.5-A.1).

Отдельная таблица `admin_audit_log` для админских мутаций (ГДД §18.6).
От общего `audit_log` отличается:

* `admin_id BIGINT NOT NULL` (FK → `admins.id`) — все записи привязаны
  к конкретному админу. У общего `audit_log.actor_id` тип `BIGINT NULL`
  (часть событий — системные / без актора).
* Контекст канала: `tg_chat_id` (для `source=bot`), `ip` (для
  `source=web`). У общего `audit_log` этих колонок нет.
* `source` ограничен whitelist-ом `bot` / `web` (CHECK). Опечатки
  отбрасываются БД.

Индексы:

* `(admin_id, occurred_at)` — основной запрос `/audit <admin>`.
* `(target_kind, target_id)` — «история действий на конкретного игрока /
  клан / балансовый ключ».
* `(action)` — фильтрация по типу команды.

Used by:

* `IAdminAuditLogger.record(...)` — Спринт 2.5-A.1.
* `application/admin/*` use-cases (Спринты 2.5-B / 2.5-C / 2.5-D)
  пишут запись в той же транзакции, что и сама мутация.
* Будущая команда `/audit` (Спринт 2.5-D, задача 2.5.7) и опциональная
  веб-панель (Спринт 4.5, задача 4.5.7) — читают из этой таблицы.

Revision ID: 0016_admin_audit_log
Revises: 0015_referrals
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016_admin_audit_log"
down_revision: str | Sequence[str] | None = "0015_referrals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_kind", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_admin_audit_log"),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["admins.id"],
            name="fk_admin_audit_log_admin_id_admins",
        ),
        # Whitelist source-ов — last-line-of-defense, дублирует
        # `AdminAuditSource` enum в домене (`bot` | `web`).
        sa.CheckConstraint(
            "source IN ('bot', 'web')",
            name="admin_audit_log_source_whitelist",
        ),
    )
    # `/audit <admin>` — основной запрос: «последние записи админа».
    op.create_index(
        "ix_admin_audit_log_admin_id_occurred_at",
        "admin_audit_log",
        ["admin_id", "occurred_at"],
    )
    # «История действий на конкретный target» (игрок 42, балансовый
    # ключ X и т. п.).
    op.create_index(
        "ix_admin_audit_log_target_kind_target_id",
        "admin_audit_log",
        ["target_kind", "target_id"],
    )
    op.create_index(
        "ix_admin_audit_log_action",
        "admin_audit_log",
        ["action"],
    )


def downgrade() -> None:
    op.drop_index("ix_admin_audit_log_action", table_name="admin_audit_log")
    op.drop_index(
        "ix_admin_audit_log_target_kind_target_id",
        table_name="admin_audit_log",
    )
    op.drop_index(
        "ix_admin_audit_log_admin_id_occurred_at",
        table_name="admin_audit_log",
    )
    op.drop_table("admin_audit_log")
