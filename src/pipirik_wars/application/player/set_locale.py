"""Use-case `SetPlayerLocale` (Спринт 1.5.F, ПД 1.5.2).

Команда `/lang ru|en` сохраняет «явный выбор языка» игрока в
`users.locale_override`. Этот override имеет приоритет в
`LocaleMiddleware`-е над автоматически определённой `Locale` из
`tg.language_code` (см. `LocaleResolver`).

Acceptance из Спринта 1.5.F (development_plan.md / current_tasks.md):
> Игрок может переключиться `/lang ru` → ответы в RU, `/lang en` →
> в EN. Выбор сохраняется в БД и переживает рестарт бота. Фоновые
> сообщения (forest-finished от scheduler-а) тоже идут в выбранной
> локали.

Реализация:

- транзакционно (`IUnitOfWork`) `players.get_by_tg_id` →
  `with_locale_override(...)` → `players.save(...)` → audit-запись
  `PLAYER_LOCALE_SET` с `before/after` снимком.
- `idempotency_key` — `set_locale:{tg_id}:{ts}`. Повторный вызов с
  той же локалью — no-op (entity не меняется → save возвращает тот
  же ряд, audit-запись всё равно пишется для трейсинга «сколько
  раз пользователь жал кнопку»; стоимость ничтожная).
- если игрок не зарегистрирован (`get_by_tg_id` → `None`), use-case
  бросает `PlayerNotFoundError` — handler покажет «нажмите /start».
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.i18n.locale import SUPPORTED_LOCALES, Locale
from pipirik_wars.domain.player import IPlayerRepository, Player, PlayerNotFoundError
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class SetPlayerLocaleResult:
    """Снимок результата.

    `previous_locale_override` / `locale_override` — старая и новая
    `users.locale_override`. `None` означает «нет override-а / сброс
    обратно к авто-определению».
    """

    player: Player
    previous_locale_override: str | None
    locale_override: str | None


class SetPlayerLocale:
    """Use-case `/lang ru|en` (выбор/сброс языка игрока)."""

    __slots__ = ("_audit", "_clock", "_players", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._audit = audit
        self._clock = clock

    async def execute(
        self,
        *,
        tg_id: int,
        locale: Locale | None,
    ) -> SetPlayerLocaleResult:
        """Сохранить `locale_override` игрока.

        `locale=None` — сбросить override обратно к
        `tg.language_code → DEFAULT_LOCALE` (полезно, если игрок
        передумал и хочет «как Telegram скажет»). На MVP handler
        `/lang` сам не открывает этот путь, но use-case его поддерживает.
        """
        new_override: str | None
        if locale is None:
            new_override = None
        else:
            if locale.code not in SUPPORTED_LOCALES:
                raise ValueError(
                    f"unsupported locale {locale.code!r}; supported: {sorted(SUPPORTED_LOCALES)!r}",
                )
            new_override = locale.code

        async with self._uow:
            player = await self._players.get_by_tg_id(tg_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=tg_id)

            previous_override = player.locale_override
            now = self._clock.now()
            updated = player.with_locale_override(new_override, now=now)
            saved = await self._players.save(updated)
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PLAYER_LOCALE_SET,
                    actor_id=saved.id,
                    target_kind="player",
                    target_id=str(saved.id) if saved.id is not None else str(tg_id),
                    before={"locale_override": previous_override},
                    after={"locale_override": new_override},
                    reason="user_lang_command",
                    idempotency_key=f"set_locale:{tg_id}:{int(now.timestamp())}",
                    occurred_at=now,
                ),
            )

        return SetPlayerLocaleResult(
            player=saved,
            previous_locale_override=previous_override,
            locale_override=new_override,
        )


__all__ = ["SetPlayerLocale", "SetPlayerLocaleResult"]
