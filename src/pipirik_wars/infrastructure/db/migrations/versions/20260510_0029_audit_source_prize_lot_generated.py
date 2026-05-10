"""Расширение whitelist `audit_log.source` источником `prize_lot_generated` (Спринт 4.1-C, C.2).

Доменный enum `AuditSource` (см. `domain/shared/ports/audit.py`) получает
одно новое значение:

* `PRIZE_LOT_GENERATED = "prize_lot_generated"` — нарезка лота из пула в
  таблицу `prize_lots` (ГДД §12.6.3). Пишется use-case-ом `GeneratePrizeLots`
  (4.1-C / Шаг C.2) сразу после `IPrizeLotRepository.add(lot)` +
  `IPrizePoolRepository.apply_increment(currency, -lot.amount_native)`
  внутри той же UoW.

Источник **не** входит ни в один rolling-window-whitelist anti-cheat-а
(`anticheat.organic_sources` / `donate_sources` / `tribe_bonus_sources`):
это пул-внутренний бухгалтерский маркер, не length-source. Парного
«cost»-source-а нет (декремент пула — внутренняя проводка, без выплаты
игроку до `ClaimPrize` 4.1-D).

CHECK-инвариант `audit_log_source_whitelist` расширяется последовательно
с момента `0007_anticheat_foundation`; предыдущее расширение —
`0028_audit_source_prize_pool_increment` (Спринт 4.1-B).

Здесь:

1. Сбрасываем CHECK через `batch_alter_table` (SQLite-совместимо).
2. Создаём новый CHECK с расширенным whitelist-ом, включающим
   `prize_lot_generated`.

Идемпотентен в рамках одного апгрейда.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029_audit_source_prize_lot_generated"
down_revision: str | Sequence[str] | None = "0028_audit_source_prize_pool_increment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Обновлённый whitelist `audit_log.source`. Должен совпадать с
# `pipirik_wars.domain.shared.ports.audit.AuditSource` — расхождение
# ловит unit-тест `tests/unit/domain/shared/ports/test_audit_source.py`.
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
    "prize_lot_generated",
    "unknown",
)

# Whitelist до 4.1-C/C.2 (для downgrade()).
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
    "prize_pool_increment",
    "unknown",
)


def _check_clause(values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"source IN ({quoted})"


def upgrade() -> None:
    """Заменить старый CHECK новым, расширенным `prize_lot_generated`."""
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
    """Откатить к whitelist 4.1-B (без `prize_lot_generated`)."""
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_PREV_SOURCE_WHITELIST),
        )
