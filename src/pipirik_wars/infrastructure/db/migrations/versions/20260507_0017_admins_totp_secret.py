"""Add `totp_secret` column to `admins` (Sprint 2.5-A.3).

Опасные admin-команды (`/ban`, `/grant_*`, `/balance_set`, `/announce`)
требуют TOTP-подтверждения 6-значным кодом из authenticator-приложения
админа (ГДД §18.6). Секрет TOTP хранится **в plain-text BASE32** в
колонке `admins.totp_secret`.

Почему plain-text:

* TOTP-секрет — не пароль; его компрометация эквивалентна компрометации
  обоих факторов разом (если злоумышленник получил доступ к БД, у
  него и так есть `tg_id` админа). Шифрование секрета теми же ключами,
  что и приложение, не повышает безопасность, а только усложняет
  ротацию.
* В будущем (Спринт 4.1+) можно ввести KMS-обёртку — миграция
  получится отдельная, без поломки текущей схемы.

`NULL` означает «у этого админа нет TOTP» — деопасные команды (`/ban`
и т. п.) для него отказываются с понятной ошибкой «вы не настроили
2FA, обратитесь к super-admin». Существующие админы (созданные до
этой миграции) автоматически получают `NULL` и должны включить TOTP
явно (Спринт 2.5-D добавит команду `/admin_setup_totp`).

Revision ID: 0017_admins_totp_secret
Revises: 0016_admin_audit_log
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017_admins_totp_secret"
down_revision: str | Sequence[str] | None = "0016_admin_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admins",
        sa.Column("totp_secret", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("admins", "totp_secret")
