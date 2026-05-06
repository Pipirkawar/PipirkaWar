"""Расширение whitelist `audit_log.source` источником `daily_head` (Спринт 2.3.C).

Доменный enum `AuditSource` (см. `domain/shared/ports/audit.py`) получает
новое значение `DAILY_HEAD = "daily_head"` — для записи `LENGTH_GRANT`-аудита,
которую делает `ILengthGranter.grant(...)` внутри use-case-а
`RequestDailyHead` / `RunDailyHeadCron` (Спринт 2.3.C).

CHECK-инвариант `audit_log_source_whitelist` был создан в миграции
`0007_anticheat_foundation` со старым набором значений. Здесь мы:

1. Сбрасываем старый CHECK через `batch_alter_table` (SQLite-совместимо).
2. Создаём новый CHECK с расширенным whitelist-ом, включающим `daily_head`.

Идемпотентен в рамках одного апгрейда: если миграция уже применена,
повторный `alembic upgrade head` — no-op (alembic_version-таблица).

Anti-cheat hardcap (`balance.anticheat.organic_sources`) тоже расширяется —
бонус Главы клана дня считается «organic» наградой, попадает под daily/weekly
cap. Соответствующая правка — в `config/balance.yaml` (отдельный конфиг,
не миграция).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_audit_source_daily_head"
down_revision: str | Sequence[str] | None = "0013_daily_active"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Обновлённый whitelist. Должен совпадать с
# `domain.shared.ports.audit.AuditSource`. Расхождение ловит unit-тест
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
    "daily_head",
    "unknown",
)

# Старый whitelist (до Спринта 2.3.C) — нужен для downgrade().
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
    "unknown",
)


def _check_clause(values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"source IN ({quoted})"


def upgrade() -> None:
    """Заменить старый CHECK новым, расширенным `daily_head`-ом."""
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_SOURCE_WHITELIST),
        )
    # Используем `sa` чтобы IDE/линтер не ругались на «unused import»;
    # alembic-runtime сам импортирует sqlalchemy.
    _ = sa


def downgrade() -> None:
    """Откатить к старому whitelist (без `daily_head`)."""
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_PREV_SOURCE_WHITELIST),
        )
