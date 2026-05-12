"""ORM-модель ``ton_connect_nonces`` — server-side nonce-store TON Connect 2.0 (Спринт 4.1-F, F.6.b).

Persistent storage для одноразовых nonce-ов, выдаваемых сервером в
phase-1 ``/link_wallet``-flow-а (``RequestLinkWalletProof``-use-case,
F.4.a) и потребляемых в phase-2 после Ed25519-verify-а в ``LinkWallet``-
use-case (F.4.b). Реализация порта ``domain/monetization/ports.py::
INonceStore`` — ``SqlAlchemyNonceStore`` в этом же спринте.

Колонки — см. миграцию ``0038_ton_connect_nonces``:

* ``nonce VARCHAR(64) PRIMARY KEY`` — server-generated nonce-значение
  (``secrets.token_urlsafe(24)`` ≈ 32 ASCII-символа; PK с запасом 64).
* ``scope VARCHAR(128) NOT NULL`` — бизнес-контекст
  (``"link_wallet:{player_id}:{currency}"``).
* ``issued_at TIMESTAMP WITH TIME ZONE NOT NULL`` — момент выдачи.
* ``consumed_at TIMESTAMP WITH TIME ZONE NULL`` — момент успешного
  ``consume_nonce(...)``-а (либо ``NULL``).
* ``expires_at TIMESTAMP WITH TIME ZONE NOT NULL`` — TTL-граница.

DB-инварианты (CHECK) — last-line-of-defense; доменный порт и use-case-
овые validators сторожат то же самое до записи.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base


class TonConnectNonceORM(Base):
    """Строка таблицы ``ton_connect_nonces`` — один server-issued nonce."""

    __tablename__ = "ton_connect_nonces"

    nonce: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "LENGTH(nonce) > 0",
            name="ck_ton_connect_nonces_nonce_non_empty",
        ),
        CheckConstraint(
            "LENGTH(scope) > 0",
            name="ck_ton_connect_nonces_scope_non_empty",
        ),
        CheckConstraint(
            "expires_at > issued_at",
            name="ck_ton_connect_nonces_expires_after_issued",
        ),
    )
