"""ORM-модели подсистемы безопасности.

Колонки JSON-типа определены через `JSON` (портабельно: Postgres → JSONB,
SQLite → TEXT-обёртка). Если в Postgres понадобится GIN-индекс по JSONB —
добавим в alembic-миграции вручную через `op.create_index`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base

# SQLite не умеет AUTOINCREMENT на BigInteger; для тестов используем
# Integer-вариант, в Postgres — нативный bigserial.
_AutoIncBigInt = BigInteger().with_variant(Integer, "sqlite")


class IdempotencyKeyORM(Base):
    """Таблица `idempotency_keys`.

    PK — сам ключ (`text`). Уникальность гарантируется PK; каждая
    мутирующая операция перед коммитом INSERT-ит ключ. Конфликт PK =
    «уже было выполнено», операция NO-OP.

    `namespace` дублируется как отдельная колонка — для удобства
    отчётности и партицирования (в Postgres) по типу операции.
    """

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (Index("ix_idempotency_keys_namespace_created_at", "namespace", "created_at"),)


class AuditLogORM(Base):
    """Таблица `audit_log`.

    Иммутабельная (никаких UPDATE/DELETE из приложения, только INSERT).
    `before`/`after` — JSON-объекты (на Postgres рекомендуется JSONB
    через альтернативный дайалект-вариант; здесь — портабельный JSON).
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    before: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # ── Спринт 1.6.A (anti-cheat hardcap) ──
    # `source` — whitelist в БД (CHECK) дублирует `AuditSource` в домене,
    # чтобы случайная опечатка в `source="forst"` не выпала из
    # агрегации anti-cheat-окна. Backfill для старых строк = 'unknown'.
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="unknown",
        index=True,
    )
    # `clamped_from` — None, если дельта не клампилась; число (исходная
    # запрошенная дельта в см), если progression.add_length подрезал её
    # под daily_cap_cm/weekly_cap_cm (Спринт 1.6.D).
    clamped_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ── Спринт 1.6.C ──
    # `delta_cm` — фактически применённая дельта длины в см (знаковая;
    # admin_refund будет отрицательной). Anti-cheat rolling-окно
    # суммирует `delta_cm > 0` с фильтром по `source IN organic_sources`.
    # NULL для не-длиновых событий (clan_register, balance_reload и т. п.).
    delta_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_audit_log_target_kind_target_id", "target_kind", "target_id"),
        Index("ix_audit_log_action", "action"),
        # Composite-индекс под anti-cheat-агрегацию (Спринт 1.6.C):
        # `WHERE target_id=:pid AND source IN (...) AND occurred_at >= :since`.
        Index(
            "ix_audit_log_target_source_occurred",
            "target_id",
            "source",
            "occurred_at",
        ),
        CheckConstraint(
            # Полный whitelist `audit_log.source` — должен совпадать с
            # `pipirik_wars.domain.shared.ports.audit.AuditSource` и с
            # whitelist-ом из последней расширяющей миграции
            # (`20260511_0034_audit_source_wallet_linked.py`).
            # Расхождение ловит unit-тест `test_audit_source.py`.
            "source IN ('forest', 'mountains', 'dungeon', 'oracle', 'referral_signup', "
            "'referral_thickness', 'pvp_reward', 'caravan_reward', 'raid_reward', "
            "'admin_grant', 'admin_refund', 'stars_payment', 'ton_payment', "
            "'usdt_payment', 'daily_head', 'roulette_free_cost', "
            "'roulette_free_reward', 'oracle_tribe_bonus', 'roulette_paid_reward', "
            "'prize_pool_increment', 'prize_lot_generated', 'prize_lot_refunded', "
            "'prize_lot_reserved', 'prize_lot_claimed', 'wallet_linked', 'unknown')",
            name="audit_log_source_whitelist",
        ),
    )


class ActivityLockORM(Base):
    """Таблица `activity_locks`.

    PK = `(actor_kind, actor_id)` — Postgres сам даст «второй INSERT
    падает». В реализации репозитория используем `INSERT ... ON CONFLICT
    DO NOTHING` для портабельности.
    """

    __tablename__ = "activity_locks"

    actor_kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    actor_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
