"""In-memory ``INonceStore`` для sandbox-режима (Спринт 4.1-F, шаг F.4.b).

Временная prod-имплементация ``INonceStore`` поверх обычного dict-а.
Используется в Container до того, как F.6.b введёт
``SqlAlchemyNonceStore`` (SQL + atomic-CAS-update).

Семантика:

* ``issue_nonce(scope, nonce, expires_at)`` — добавляет запись
  ``(scope, nonce) → (expires_at, consumed=False)`` в in-memory dict.
  При повторном issue одного и того же ``(scope, nonce)`` бросает
  ``ValueError`` (контракт ``INonceStore``: не выдавать nonce дважды).
* ``consume_nonce(scope, nonce, now)`` — атомарный CAS-consume:
  возвращает ``True`` если запись существует, не consumed и не expired
  (и помечает её consumed=True); иначе ``False``.

In-memory реализация ОК для sandbox/testnet и unit-тестов; для
production-нагрузки и persistence через restart-ы нужен
``SqlAlchemyNonceStore`` (F.6.b).

⚠ Не сохраняет данные между перезапусками процесса. Игрок, получивший
nonce в phase-1 и переподключившийся после рестарта бота — потеряет
nonce и должен запросить новый. Это приемлемо для sandbox-testnet.

Thread-safety: in-memory dict не защищён мьютексом. asyncio-runtime
бота однопоточный (event-loop), параллельных await-ов внутри
``consume_nonce`` нет (между ``get`` и ``set`` нет await-point-а), так
что в рамках single-event-loop CAS-семантика сохраняется.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import structlog

__all__ = ["InMemoryNonceStore"]

_logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class _Entry:
    expires_at: datetime
    consumed: bool


class InMemoryNonceStore:
    """In-memory имплементация ``INonceStore`` (Спринт 4.1-F, шаг F.4.b)."""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], _Entry] = {}

    async def issue_nonce(
        self,
        *,
        scope: str,
        nonce: str,
        expires_at: datetime,
    ) -> None:
        """См. ``INonceStore.issue_nonce``."""
        key = (scope, nonce)
        if key in self._entries:
            raise ValueError(
                f"InMemoryNonceStore: nonce already issued for scope={scope!r} "
                f"nonce={nonce!r} (use-case must generate unique nonces)",
            )
        self._entries[key] = _Entry(expires_at=expires_at, consumed=False)
        _logger.debug(
            "ton_connect.nonce_store.issued",
            scope=scope,
            expires_at=expires_at.isoformat(),
        )

    async def consume_nonce(
        self,
        *,
        scope: str,
        nonce: str,
        now: datetime,
    ) -> bool:
        """См. ``INonceStore.consume_nonce``."""
        key = (scope, nonce)
        entry = self._entries.get(key)
        if entry is None:
            return False
        if entry.consumed:
            return False
        if entry.expires_at <= now:
            return False
        entry.consumed = True
        return True
