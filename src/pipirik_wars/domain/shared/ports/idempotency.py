"""Идемпотентность.

Каждая мутация (`add_length`, `assign_daily_head`, `referral_milestone`)
помечается `idempotency_key`. Если ключ уже встречался — операция NO-OP.

Ключи генерируются детерминированно из бизнес-смысла операции:
например, `(user_id, "referral_signup")` или
`(clan_id, moscow_date, "daily_head")`. Это гарантирует, что повторный
запуск джобы или ретрай вебхука не приведут к двойным начислениям.
ГДД §0 — «идемпотентность всех мутирующих операций».
"""

from __future__ import annotations

import abc
from collections.abc import Sequence


class IIdempotencyKey(abc.ABC):
    """Сервис идемпотентности.

    Кладётся в `application`-use-case. Реализация — таблица
    `idempotency_keys` в БД (см. `development_plan.md` §2.3).
    """

    @abc.abstractmethod
    def build(self, namespace: str, parts: Sequence[str]) -> str:
        """Собрать ключ из namespace и значимых частей.

        Возвращает строку, длина которой влезает в Postgres-индекс
        (`text` колонка с unique-индексом, ≤ 255 символов).
        """

    @abc.abstractmethod
    async def is_seen(self, key: str) -> bool:
        """Проверить, уже выполнялась ли операция с этим ключом."""

    @abc.abstractmethod
    async def mark(self, key: str, *, namespace: str) -> None:
        """Зафиксировать, что операция выполнена.

        Вызывается **внутри** той же транзакции, что и сама мутация —
        иначе теряется атомарность. См. `IUnitOfWork`.
        """
