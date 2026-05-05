"""Users locale override column (Sprint 1.5.F).

Добавляем `users.locale_override TEXT NULL` для команды `/lang ru|en`
(ПД 1.5.2 / Спринт 1.5.F). NULL означает «нет override-а» — в этом
случае `LocaleMiddleware` фоллбэчит на `tg.language_code → DEFAULT_LOCALE`.

Revision ID: 0006_users_locale_override
Revises: 0005_oracle_invocations
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_users_locale_override"
down_revision: str | Sequence[str] | None = "0005_oracle_invocations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL = нет override-а. CHECK ограничивает значения двумя поддерживаемыми
    # локалями MVP (ru / en); расширение каталога — в Спринте 4.1.7.
    # `batch_alter_table` нужен для SQLite (dev/тесты): SQLite не умеет
    # ALTER ... ADD CONSTRAINT, поэтому Alembic делает copy-and-move.
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("locale_override", sa.String(length=8), nullable=True),
        )
        batch.create_check_constraint(
            "users_locale_override_supported",
            "locale_override IS NULL OR locale_override IN ('ru', 'en')",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint(
            "users_locale_override_supported",
            type_="check",
        )
        batch.drop_column("locale_override")
