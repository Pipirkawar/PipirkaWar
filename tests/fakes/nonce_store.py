"""In-memory ``INonceStore`` для тестов (Спринт 4.1-F, шаг F.3).

Используется в:

* unit-тестах use-case-ов 4.1-F ``RequestLinkWalletProof`` (F.4.a) и
  ``LinkWallet`` (F.4.b) для изоляции от SQL-репо.
* integration-тестах bot-handler-ов ``/link_wallet*`` (F.8.a/b) до
  appearance-а реального ``SqlAlchemyNonceStore`` (F.6.b).

Контракт ``FakeNonceStore`` идентичен ``INonceStore``:

* ``issue_nonce(*, scope, nonce, expires_at)`` — кладёт запись
  ``(scope, nonce) → (expires_at, consumed=False)`` в in-memory dict.
  Бросает ``ValueError`` если такой ``(scope, nonce)`` уже зарегистрирован
  (контракт ``INonceStore``: не выдавать один и тот же nonce дважды).
* ``consume_nonce(*, scope, nonce, now)`` — атомарный CAS-consume,
  пометить consumed=True и вернуть ``True``, либо ``False`` если:
    * ``(scope, nonce)`` никогда не выдавался;
    * уже consumed;
    * ``expires_at <= now``.

In-memory реализация не имеет реального race-condition (один поток в
тестах), но семантика «consume_nonce → True ровно один раз» сохраняется.

Также экспонирует counter-ы вызовов и helper-ы для assert-ов:

* ``issue_calls`` / ``consume_calls`` — list-ы dict-кортежей всех
  вызовов в порядке.
* ``is_consumed(scope, nonce)`` / ``is_known(scope, nonce)`` — для
  whitebox-проверок в тестах.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class _Entry:
    expires_at: datetime
    consumed: bool


class FakeNonceStore:
    """Маркерная in-memory реализация ``INonceStore`` (Спринт 4.1-F)."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], _Entry] = {}
        self.issue_calls: list[dict[str, object]] = []
        self.consume_calls: list[dict[str, object]] = []

    async def issue_nonce(
        self,
        *,
        scope: str,
        nonce: str,
        expires_at: datetime,
    ) -> None:
        self.issue_calls.append(
            {"scope": scope, "nonce": nonce, "expires_at": expires_at},
        )
        key = (scope, nonce)
        if key in self._entries:
            raise ValueError(
                f"FakeNonceStore: nonce already issued for scope={scope!r} "
                f"nonce={nonce!r} (use-case must generate unique nonces)",
            )
        self._entries[key] = _Entry(expires_at=expires_at, consumed=False)

    async def consume_nonce(
        self,
        *,
        scope: str,
        nonce: str,
        now: datetime,
    ) -> bool:
        self.consume_calls.append(
            {"scope": scope, "nonce": nonce, "now": now},
        )
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

    # ---- helpers for whitebox tests ----

    def is_known(self, *, scope: str, nonce: str) -> bool:
        return (scope, nonce) in self._entries

    def is_consumed(self, *, scope: str, nonce: str) -> bool:
        entry = self._entries.get((scope, nonce))
        return entry is not None and entry.consumed


__all__ = ["FakeNonceStore"]
