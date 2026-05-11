"""Расширение whitelist `audit_log.source` источником `prize_lot_reserved` (Спринт 4.1-C, C.6.a).

Доменный enum `AuditSource` (см. `domain/shared/ports/audit.py`) получает
одно новое значение:

* `PRIZE_LOT_RESERVED = "prize_lot_reserved"` — резервирование лота на
  спине (`PrizeLot.status: ACTIVE → RESERVED`, ГДД §12.6.5). Будет
  писаться use-case-ами `SpinPaidRoulette` / `SpinFreeRoulette` (C.6.c)
  внутри той же UoW, что и `IPrizeLotRepository.update_status(lot_id,
  RESERVED)` — когда picker рулетки вернул `RouletteOutcome.crypto_lot(
  lot_id=...)` (C.5).

Источник **не** входит ни в один rolling-window-whitelist anti-cheat-а
(`anticheat.organic_sources` / `donate_sources` / `tribe_bonus_sources`):
это статус-маркер лота, не length-source. Парного «cost»-source-а нет
(декремент пула уже произошёл в `GeneratePrizeLots`).

CHECK-инвариант `audit_log_source_whitelist` расширяется последовательно
с момента `0007_anticheat_foundation`; предыдущее расширение —
`0031_audit_source_prize_lot_refunded` (Спринт 4.1-C, C.4).

Здесь:

1. Сбрасываем CHECK через `batch_alter_table` (SQLite-совместимо).
2. Создаём новый CHECK с расширенным whitelist-ом, включающим
   `prize_lot_reserved`.

Идемпотентен в рамках одного апгрейда.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0032_audit_source_prize_lot_reserved"
down_revision: str | Sequence[str] | None = "0031_audit_source_prize_lot_refunded"
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
    "prize_lot_refunded",
    "prize_lot_reserved",
    "unknown",
)

# Whitelist до 4.1-C/C.6.a (для downgrade()).
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
    "prize_lot_generated",
    "prize_lot_refunded",
    "unknown",
)


def _check_clause(values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"source IN ({quoted})"


def upgrade() -> None:
    """Заменить старый CHECK новым, расширенным `prize_lot_reserved`."""
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
    """Откатить к whitelist 4.1-C/C.4 (без `prize_lot_reserved`)."""
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("audit_log_source_whitelist", type_="check")
        batch.create_check_constraint(
            "audit_log_source_whitelist",
            _check_clause(_PREV_SOURCE_WHITELIST),
        )
