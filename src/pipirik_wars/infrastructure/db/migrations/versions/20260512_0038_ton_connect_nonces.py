"""Server-side nonce-store для TON Connect 2.0 verify (Спринт 4.1-F, F.6.a).

Новая таблица ``ton_connect_nonces`` — persistent storage для одноразовых
nonce-ов, выдаваемых сервером в phase-1 ``/link_wallet``-flow-а
(``RequestLinkWalletProof``-use-case, F.4.a) и потребляемых в phase-2
после Ed25519-verify-а в ``LinkWallet``-use-case (F.4.b). Реализация
порта ``domain/monetization/ports.py::INonceStore`` (F.3) — SQLAlchemy-
адаптер ``SqlAlchemyNonceStore`` в F.6.b.

Назначение nonce-store-а — anti-replay-защита TON Connect-proof-ов: без
server-side memorising «какой nonce был выдан / consumed» атакующий
сможет перехватить proof в transit-е и повторно использовать его на
другой стороне приложения, либо повторно подписать тем же ключом любую
дальнейшую попытку привязки. Атомарный CAS-consume гарантирует, что
ровно один параллельный запрос вернёт ``True``, остальные — ``False``.

Колонки:

* ``nonce VARCHAR(64) PRIMARY KEY`` — собственно nonce-значение. Server
  генерирует ``secrets.token_urlsafe(24)`` (≈32 ASCII-символа, URL-safe-
  base64), но PK-длина с запасом (64) для будущих формат-расширений
  (например, добавления prefix-а версии).
* ``scope VARCHAR(128) NOT NULL`` — бизнес-контекст
  (``"link_wallet:{player_id}:{currency}"``). Длина 128 — с запасом:
  player_id ≤ 19 цифр (BigInt), currency ≤ 16 символов
  (``usdt_decimal``), namespace-prefix ≤ 16. Итого реалистично ≤ 60,
  лимит 128 защищает от ошибок генератора scope-а.
* ``issued_at TIMESTAMP WITH TIME ZONE NOT NULL`` — момент выдачи через
  ``issue_nonce(...)``.
* ``consumed_at TIMESTAMP WITH TIME ZONE NULL`` — момент успешного
  ``consume_nonce(...)``-а (либо ``NULL``, если ещё не использован).
* ``expires_at TIMESTAMP WITH TIME ZONE NOT NULL`` — TTL-граница
  (``issued_at + ttl``). После ``expires_at`` nonce невалиден независимо
  от ``consumed_at`` (защита от долго-валидных proof-ов даже если
  attacker раздобыл их в transit-е).

Инварианты (CHECK):

* ``ck_ton_connect_nonces_nonce_non_empty`` — ``LENGTH(nonce) > 0``.
  Last-line-of-defense; ``INonceStore.issue_nonce`` контракт
  гарантирует non-empty.
* ``ck_ton_connect_nonces_scope_non_empty`` — ``LENGTH(scope) > 0``.
* ``ck_ton_connect_nonces_expires_after_issued`` — ``expires_at >
  issued_at``. Защита от bug-а в use-case-е: TTL не может быть
  нулевым или отрицательным.

Индексы:

* ``ix_ton_connect_nonces_expires_at`` ON ``(expires_at)`` — cleanup-job
  ``DELETE FROM ton_connect_nonces WHERE expires_at < now() - retention``
  будет работать index-scan-ом, а не full-table-scan-ом, по мере того
  как таблица вырастает.
* ``ix_ton_connect_nonces_scope_nonce_consumed_at`` ON
  ``(scope, nonce, consumed_at)`` — покрывающий индекс для atomic-CAS-
  consume-а в ``SqlAlchemyNonceStore.consume_nonce``-е (F.6.b). Хотя PK
  на ``nonce`` уже покрывает ``WHERE nonce=?``-условие, дополнительный
  composite-индекс полезен для cleanup-/мониторинг-запросов по scope-у
  и для статистики «сколько активных nonce-ов в scope X».

CHECK-инварианты — last-line-of-defense; доменный порт ``INonceStore``
и use-case-овые validators сторожат то же самое до записи.

Retention-политика nonce-записей за пределами скоупа этой миграции:
старые consumed/expired-записи остаются в таблице как audit-trail и
чистятся отдельным cron-job-ом (F.7 ввёл бы его, но в рамках 4.1-F
out-of-scope — добавим в backlog 4.1-G/4.1-H). С учётом TTL ≈ 5 минут
и ожидаемого RPS ``/link_wallet`` ≪ 1 RPS, таблица не вырастет до
гигабайтов даже при отсутствии cleanup-а на горизонте месяцев.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_ton_connect_nonces"
down_revision: str | Sequence[str] | None = "0037_payout_freeze_and_prize_lot_winner_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ton_connect_nonces",
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("nonce", name="pk_ton_connect_nonces"),
        sa.CheckConstraint(
            "LENGTH(nonce) > 0",
            name="ck_ton_connect_nonces_nonce_non_empty",
        ),
        sa.CheckConstraint(
            "LENGTH(scope) > 0",
            name="ck_ton_connect_nonces_scope_non_empty",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name="ck_ton_connect_nonces_expires_after_issued",
        ),
    )
    op.create_index(
        "ix_ton_connect_nonces_expires_at",
        "ton_connect_nonces",
        ["expires_at"],
    )
    op.create_index(
        "ix_ton_connect_nonces_scope_nonce_consumed_at",
        "ton_connect_nonces",
        ["scope", "nonce", "consumed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ton_connect_nonces_scope_nonce_consumed_at",
        table_name="ton_connect_nonces",
    )
    op.drop_index(
        "ix_ton_connect_nonces_expires_at",
        table_name="ton_connect_nonces",
    )
    op.drop_table("ton_connect_nonces")
