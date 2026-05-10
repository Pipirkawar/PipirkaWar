"""Расширение whitelist `audit_log.source` источником `prize_pool_increment` (Спринт 4.1-B, B.4).

Доменный enum `AuditSource` (см. `domain/shared/ports/audit.py`) получает
одно новое значение:

* `PRIZE_POOL_INCREMENT = "prize_pool_increment"` — донат-инкремент
  призового пула (10% от подтверждённого платежа, ГДД §12.6.1). Пишется
  use-case-ом `RecordDonation` (4.1-B / Шаг B.4) сразу после
  `IPrizePoolRepository.apply_increment(...)` внутри той же UoW.

Источник **не** входит ни в один rolling-window-whitelist anti-cheat-а
(`anticheat.organic_sources` / `donate_sources` / `tribe_bonus_sources`):
это пул-внутренний бухгалтерский маркер, не length-source. Cost-сторона
платежа (10% которого утекло в пул) пишется отдельной audit-записью с
`source IN (STARS_PAYMENT, TON_PAYMENT, USDT_PAYMENT)` (см. `0026`).

CHECK-инвариант `audit_log_source_whitelist` был создан в миграции
`0007_anticheat_foundation` со старым набором значений и расширялся:
- `0014` — `daily_head`,
- `0018` — `mountains` / `dungeon`,
- `0024` — `roulette_free_cost` / `roulette_free_reward`,
- `0025` — `oracle_tribe_bonus`,
- `0026` — `roulette_paid_reward`.

Здесь мы:

1. Сбрасываем CHECK через `batch_alter_table` (SQLite-совместимо).
2. Создаём новый CHECK с расширенным whitelist-ом, включающим
   `prize_pool_increment`.

Идемпотентен в рамках одного апгрейда.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028_audit_source_prize_pool_increment"
down_revision: str | Sequence[str] | None = "0027_prize_pool_balance"
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
    "roulette_paid_reward",
    "prize_pool_increment",
    "unknown",
)

# Whitelist до 4.1-B (для downgrade()).
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
    "oracle_tribe_bonus",
    "roulette_paid_reward",
    "unknown",
)


def _check_clause(values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"source IN ({quoted})"


def upgrade() -> None:
    """Заменить старый CHECK новым, расширенным `prize_pool_increment`."""
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
    """Откатить к старому whitelist (без `prize_pool_increment`)."""
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_PREV_SOURCE_WHITELIST),
        )
