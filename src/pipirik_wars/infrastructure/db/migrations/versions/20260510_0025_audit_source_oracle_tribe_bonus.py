"""Расширение whitelist `audit_log.source` источником `oracle_tribe_bonus` (Спринт 3.6-A).

Доменный enum `AuditSource` (см. `domain/shared/ports/audit.py`) получает
одно новое значение:

* `ORACLE_TRIBE_BONUS = "oracle_tribe_bonus"` — отдельная проводка
  `LENGTH_GRANT` для бонус-за-племена в `/predict` (ГДД §11.1).
  Дельта `+min(n_active_tribes * cm_per_tribe, cap_cm)` см добавляется
  поверх базового `oracle`-розыгрыша.

Источник **не** входит в `anticheat.organic_sources` (см. `balance.yaml`):
бонус-за-племена не должен учитываться в anti-cheat-окнах 24h/7d, чтобы
крупные кланы не блокировали органический прирост у своих участников.
Семантически он сидит в отдельном `tribe_bonus_sources`-whitelist
(см. `AnticheatConfig.tribe_bonus_sources`); это audit-only маркер
для финансового аудита и админ-просмотра, аналогично паре
`roulette_free_cost`/`roulette_free_reward` (Спринт 3.5-C).

CHECK-инвариант `audit_log_source_whitelist` был создан в миграции
`0007_anticheat_foundation` со старым набором значений, расширён в `0014`
(`daily_head`), `0018` (`mountains`/`dungeon`) и `0024` (`roulette_free_*`).
Здесь мы:

1. Сбрасываем CHECK через `batch_alter_table` (SQLite-совместимо).
2. Создаём новый CHECK с расширенным whitelist-ом, включающим
   `oracle_tribe_bonus`.

Идемпотентен в рамках одного апгрейда.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025_audit_source_oracle_tribe_bonus"
down_revision: str | Sequence[str] | None = "0024_audit_source_roulette_free"
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
    "oracle_tribe_bonus",
    "unknown",
)

# Whitelist до 3.6-A (для downgrade()).
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
    "roulette_free_cost",
    "roulette_free_reward",
    "unknown",
)


def _check_clause(values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"source IN ({quoted})"


def upgrade() -> None:
    """Заменить старый CHECK новым, расширенным `oracle_tribe_bonus`."""
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
    """Откатить к старому whitelist (без `oracle_tribe_bonus`)."""
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_PREV_SOURCE_WHITELIST),
        )
