"""ORM-модель `admin_audit_log` (Спринт 2.5-A.1).

Отдельная таблица для админских мутаций (ГДД §18.6). От общего
`audit_log` отличается обязательным `admin_id` (FK → `admins.id`),
контекстом канала (`tg_chat_id` / `ip` / `source`) и узким whitelist-ом
`source`-ов (`bot` / `web`).

JSON-колонки `before` / `after` через портабельный `JSON` —
Postgres сериализует их как JSONB-совместимый JSON, SQLite (тесты) —
как TEXT-обёртку.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base

# SQLite не умеет AUTOINCREMENT на BigInteger — для тестов Integer-вариант,
# в Postgres — нативный bigserial. Тот же паттерн, что и в `AuditLogORM`.
_AutoIncBigInt = BigInteger().with_variant(Integer, "sqlite")


class AdminAuditLogORM(Base):
    """Таблица `admin_audit_log` — иммутабельный лог админских мутаций.

    Никаких UPDATE/DELETE из приложения, только INSERT. Все связки
    с конкретным админом — через `admin_id` (FK NOT NULL); если админ
    впоследствии деактивирован, исторические записи остаются (FK без
    `ON DELETE` — Postgres не позволит удалить админа с записями).
    """

    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("admins.id"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    before: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    tg_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        # /audit <admin> — основной запрос: «последние записи админа».
        Index(
            "ix_admin_audit_log_admin_id_occurred_at",
            "admin_id",
            "occurred_at",
        ),
        # /audit на конкретный target (например, «история действий на
        # игрока 42») — тот же индекс, что у общего audit_log.
        Index(
            "ix_admin_audit_log_target_kind_target_id",
            "target_kind",
            "target_id",
        ),
        Index("ix_admin_audit_log_action", "action"),
        # Whitelist source-ов — last-line-of-defense, дублирует
        # `AdminAuditSource` enum в домене. Расширяется одной миграцией
        # в день добавления новых каналов (CLI и т. п.).
        CheckConstraint(
            "source IN ('bot', 'web')",
            name="admin_audit_log_source_whitelist",
        ),
    )
