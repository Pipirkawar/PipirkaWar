"""Расширение whitelist `audit_log.source` источниками рулетки (Спринт 3.5-C).

Доменный enum `AuditSource` (см. `domain/shared/ports/audit.py`) получает
два новых значения:

* `ROULETTE_FREE_COST = "roulette_free_cost"` — списание стоимости free-spin-а
  (delta=-100 см). Пишется в `audit_log` use-case-ом `SpinFreeRoulette`.
* `ROULETTE_FREE_REWARD = "roulette_free_reward"` — выдача length-награды
  (delta=+roll см). Пишется только при LENGTH-исходе.

Оба источника **не** входят в `anticheat.organic_sources` (см. `balance.yaml`):
рулетка zero-sum-нейтральна для LENGTH-исхода (cost+reward) и cost-only для
остальных исходов; органический прирост длины не учитывается, поэтому
в anti-cheat 24h/7d-окнах эти source-ы игнорируются. Это audit-only
маркеры для финансового аудита и админ-просмотра.

CHECK-инвариант `audit_log_source_whitelist` был создан в миграции
`0007_anticheat_foundation` со старым набором значений, расширён в `0014`
(`daily_head`) и `0018` (`mountains`/`dungeon`). Здесь мы:

1. Сбрасываем CHECK через `batch_alter_table` (SQLite-совместимо).
2. Создаём новый CHECK с расширенным whitelist-ом, включающим оба
   roulette-source-а.

Идемпотентен в рамках одного апгрейда.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024_audit_source_roulette_free"
down_revision: str | Sequence[str] | None = "0023_roulette_spins"
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
    "roulette_free_cost",
    "roulette_free_reward",
    "unknown",
)

# Whitelist до 3.5-C (для downgrade()).
_PREV_SOURCE_WHITELIST: tuple[str, ...] = (
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


def _check_clause(values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"source IN ({quoted})"


def upgrade() -> None:
    """Заменить старый CHECK новым, расширенным `roulette_free_*`."""
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_SOURCE_WHITELIST),
        )
    # Используем `sa`, чтобы IDE/линтер не ругались на «unused import»;
    # alembic-runtime сам импортирует sqlalchemy.
    _ = sa


def downgrade() -> None:
    """Откатить к старому whitelist (без roulette_free_* источников)."""
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_PREV_SOURCE_WHITELIST),
        )
