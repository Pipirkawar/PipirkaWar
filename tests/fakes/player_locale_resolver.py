"""`FakePlayerLocaleResolver` — тестовая реализация `IPlayerLocaleResolver`.

In-memory `dict[tg_id -> Locale]` без БД. Тесты явно настраивают
`set_override(tg_id, locale)`; `resolve_for_tg_id` возвращает
сохранённую локаль или `None`. Дополнительно отслеживается список
вызовов `calls`, чтобы тесты могли проверить, что middleware/notifier
действительно делает резолв.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pipirik_wars.application.i18n import IPlayerLocaleResolver, Locale


@dataclass
class FakePlayerLocaleResolver(IPlayerLocaleResolver):
    """In-memory резолвер локали игрока."""

    overrides: dict[int, Locale] = field(default_factory=dict)
    calls: list[int] = field(default_factory=list)

    def set_override(self, tg_id: int, locale: Locale | None) -> None:
        if locale is None:
            self.overrides.pop(tg_id, None)
        else:
            self.overrides[tg_id] = locale

    async def resolve_for_tg_id(self, tg_id: int) -> Locale | None:
        self.calls.append(tg_id)
        return self.overrides.get(tg_id)


__all__ = ["FakePlayerLocaleResolver"]
