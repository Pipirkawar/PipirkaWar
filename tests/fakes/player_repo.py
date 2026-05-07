"""In-memory реализация `IPlayerRepository` для unit-тестов use-case-ов.

Старается воспроизводить поведение SQLAlchemy-репозитория настолько,
насколько это релевантно бизнес-логике: UNIQUE по `tg_id` бросает
`PlayerAlreadyRegisteredError`; `add()` без `id` — выдаёт следующий
по порядку serial; `save()` без существующего `id` — `IntegrityError`.

Не реализуем «откат» данных при rollback — использующие тесты сами
должны это учитывать (см. `FakeUnitOfWork`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from pipirik_wars.domain.player import (
    BroadcastRecipient,
    IPlayerRepository,
    Player,
    PlayerAlreadyRegisteredError,
    PlayerStatus,
)
from pipirik_wars.shared.errors import IntegrityError


@dataclass
class FakePlayerRepository(IPlayerRepository):
    rows: list[Player] = field(default_factory=list)

    async def get_by_tg_id(self, tg_id: int) -> Player | None:
        for p in self.rows:
            if p.tg_id == tg_id:
                return p
        return None

    async def get_by_id(self, *, player_id: int) -> Player | None:
        for p in self.rows:
            if p.id == player_id:
                return p
        return None

    async def add(self, player: Player) -> Player:
        if player.id is not None:
            raise IntegrityError(f"Player with pre-set id={player.id} cannot be added; use save()")
        if any(existing.tg_id == player.tg_id for existing in self.rows):
            raise PlayerAlreadyRegisteredError(tg_id=player.tg_id)
        new_id = (max((p.id or 0 for p in self.rows), default=0)) + 1
        saved = replace(player, id=new_id)
        self.rows.append(saved)
        return saved

    async def save(self, player: Player) -> Player:
        if player.id is None:
            raise IntegrityError("Player without id cannot be saved; use add() for new players")
        for i, existing in enumerate(self.rows):
            if existing.id == player.id:
                self.rows[i] = player
                return player
        raise IntegrityError(f"Player id={player.id} does not exist")

    async def find_by_query(self, *, query: str, limit: int) -> Sequence[Player]:
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        normalized = query.strip()
        if not normalized:
            return ()

        # 1) Целое число → точный tg_id.
        if _looks_like_int(normalized):
            tg_id = int(normalized)
            for p in self.rows:
                if p.tg_id == tg_id:
                    return (p,)
            return ()

        # 2) `@username` → точный username.
        if normalized.startswith("@") and len(normalized) > 1:
            username_value = normalized[1:]
            for p in self.rows:
                if p.username is not None and p.username.value == username_value:
                    return (p,)
            return ()

        # 3) ILIKE по username/name. Имитация PG ILIKE — case-insensitive.
        needle = normalized.casefold()
        matches: list[Player] = []
        for p in self.rows:
            username = p.username.value.casefold() if p.username is not None else ""
            name = p.name.value.casefold() if p.name is not None else ""
            if needle in username or needle in name:
                matches.append(p)
        matches.sort(key=lambda p: p.id or 0)
        return tuple(matches[:limit])

    async def list_top_by_length(self, *, limit: int) -> Sequence[Player]:
        active = [p for p in self.rows if p.status == PlayerStatus.ACTIVE]
        # Сортировка: сперва по убыванию длины, затем по возрастанию id
        # (стабильный тай-брейкер, как в SqlAlchemy-репо).
        active.sort(key=lambda p: (-p.length.cm, p.id or 0))
        return tuple(active[:limit])

    async def list_active_for_broadcast(
        self,
        *,
        locale_filter: str,
    ) -> Sequence[BroadcastRecipient]:
        if locale_filter not in ("ru", "en", "all"):
            raise ValueError(
                f"unsupported locale_filter={locale_filter!r}; expected one of: ru, en, all",
            )

        def _matches(player: Player) -> bool:
            if locale_filter == "all":
                return True
            if locale_filter == "ru":
                return player.locale_override == "ru"
            # locale_filter == "en"
            return player.locale_override == "en" or player.locale_override is None

        active = [p for p in self.rows if p.status == PlayerStatus.ACTIVE and _matches(p)]
        active.sort(key=lambda p: p.id or 0)
        return tuple(
            BroadcastRecipient(
                tg_id=p.tg_id,
                effective_locale=p.locale_override or "en",
            )
            for p in active
        )


def _looks_like_int(value: str) -> bool:
    if not value:
        return False
    body = value[1:] if value[0] in "+-" else value
    return body.isdigit()
