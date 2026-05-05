"""Anti-cheat hardcap foundation (Sprint 1.6.A).

Добавляем БД-фундамент для anti-cheat hardcap-а (ГДД §3.3 / development_plan.md
§4 ПД 1.6.1):

- `users.anticheat_ban_until TIMESTAMPTZ NULL` — до этой точки игрок в soft-ban-е
  (запрет получать длину/толщину). NULL = нет бана. Реализация trip-wire-a и
  гейтов — Спринты 1.6.D/1.6.E.
- `audit_log.source TEXT NOT NULL` — источник записи. Whitelist через CHECK
  (дублирует `domain.shared.ports.audit.AuditSource`). Старые строки backfill-ятся
  как `'unknown'`. Anti-cheat агрегация (Спринт 1.6.C) считает только organic-источники.
- `audit_log.clamped_from INT NULL` — заполняется только если
  `progression.add_length` (Спринт 1.6.D) подрезал дельту под лимит. NULL = не клампилось.

Индекс на `audit_log.source` нужен для дешёвой фильтрации в Спринте 1.6.C
(`SELECT SUM(...) FROM audit_log WHERE source IN ('forest', 'oracle', ...) AND ts > now() - 24h`).

Revision ID: 0007_anticheat_foundation
Revises: 0006_users_locale_override
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_anticheat_foundation"
down_revision: str | Sequence[str] | None = "0006_users_locale_override"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Whitelist whitelist source-ов — должен совпадать с
# `domain.shared.ports.audit.AuditSource`. Если расходится — упадёт integration-тест
# `test_audit_source_whitelist_matches_db_check`.
_SOURCE_WHITELIST: tuple[str, ...] = (
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
    "unknown",
)


def _source_check_clause() -> str:
    quoted = ", ".join(f"'{value}'" for value in _SOURCE_WHITELIST)
    return f"source IN ({quoted})"


def upgrade() -> None:
    # ── users.anticheat_ban_until ──
    # Просто nullable-колонка, никаких CHECK-инвариантов: значение в прошлом —
    # это «бан истёк естественным образом, проверять не нужно».
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "anticheat_ban_until",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        batch.create_index(
            "ix_users_anticheat_ban_until",
            ["anticheat_ban_until"],
        )

    # ── audit_log.source / audit_log.clamped_from ──
    # 1) добавляем `source` как nullable, чтобы суметь backfill-ить;
    # 2) backfill 'unknown' на все исторические строки;
    # 3) ALTER COLUMN ... SET NOT NULL;
    # 4) добавляем CHECK-whitelist + индекс по source.
    # batch_alter_table в SQLite делает copy-and-move, поэтому весь блок
    # объединён в одну транзакцию (без явного begin — alembic сам всё оборачивает).
    with op.batch_alter_table("audit_log") as batch:
        batch.add_column(
            sa.Column("clamped_from", sa.Integer(), nullable=True),
        )
        batch.add_column(
            sa.Column(
                "source",
                sa.String(length=32),
                nullable=False,
                server_default="unknown",
            ),
        )
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _source_check_clause(),
        )
        batch.create_index("ix_audit_log_source", ["source"])

    # Backfill существующих строк (на чистой БД — no-op, UPDATE по 0 строкам).
    # Делаем явно, чтобы при upgrade поверх «грязной» dev-БД пред-1.6.A эпохи
    # не остаться с серверным дефолтом, а получить детерминированное значение.
    op.execute("UPDATE audit_log SET source = 'unknown' WHERE source IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_index("ix_audit_log_source")
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.drop_column("source")
        batch.drop_column("clamped_from")

    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_anticheat_ban_until")
        batch.drop_column("anticheat_ban_until")
