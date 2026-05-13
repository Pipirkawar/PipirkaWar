"""Extend users.locale_override CHECK to 8 locales (Sprint 4.1-K).

Расширяем CHECK-constraint на `users.locale_override` с двух MVP-локалей
(`ru`, `en`) до восьми (Спринт 4.1-K, задача 4.1.14 ПД §7):
+ `pt`, `es`, `tr`, `id`, `fa`, `uk`. Это обратно-совместимое расширение
(только добавляются новые валидные значения; ранее сохранённые `ru`/`en`
остаются валидными).

Соответствующий `UserORM.__table_args__` CheckConstraint обновляется
параллельно (`src/pipirik_wars/infrastructure/db/models/player.py`).

Revision ID: 0039_users_locale_override_extended_languages
Revises: 0038_ton_connect_nonces
Create Date: 2026-05-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0039_users_locale_override_extended_languages"
down_revision: str | Sequence[str] | None = "0038_ton_connect_nonces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CONSTRAINT_NAME = "users_locale_override_supported"
_NEW_CHECK = (
    "locale_override IS NULL OR locale_override IN ('ru', 'en', 'pt', 'es', 'tr', 'id', 'fa', 'uk')"
)
_OLD_CHECK = "locale_override IS NULL OR locale_override IN ('ru', 'en')"


def upgrade() -> None:
    # SQLite не умеет ALTER CONSTRAINT — Alembic делает copy-and-move
    # через `batch_alter_table`. Drop + recreate с расширенным списком.
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint(_CONSTRAINT_NAME, type_="check")
        batch.create_check_constraint(_CONSTRAINT_NAME, _NEW_CHECK)


def downgrade() -> None:
    # Откат к двум MVP-локалям. Перед откатом потребитель должен
    # удалить или переписать строки с расширенными locale_override,
    # иначе drop+recreate (со старым CHECK) не сможет провалидировать
    # существующие данные — мы сюда не пытаемся «спасать» данные.
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint(_CONSTRAINT_NAME, type_="check")
        batch.create_check_constraint(_CONSTRAINT_NAME, _OLD_CHECK)
