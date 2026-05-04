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

    __table_args__ = (
        Index("ix_audit_log_target_kind_target_id", "target_kind", "target_id"),
        Index("ix_audit_log_action", "action"),
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
