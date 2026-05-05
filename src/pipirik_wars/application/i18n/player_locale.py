"""`IPlayerLocaleResolver` — порт «вычислить `Locale` для игрока» (Спринт 1.5.F).

Когда фоновый job (например, `TelegramForestFinishNotifier` из APScheduler)
шлёт сообщение «лес завершён», у него на руках только `tg_id` игрока —
нет ни `Update`-а, ни `tg.language_code`. Нужно сходить в `users` и
посмотреть, выставлен ли `locale_override`. Это и есть `IPlayerLocaleResolver`.

Стратегия резолва (в реализации):

1. `users.locale_override` — если задан, используется как есть.
2. Если override нет, фолбэк на `DEFAULT_LOCALE` (Locale("en")). Telegram
   `language_code` в фоновых jobs недоступен — это by design (см. ПД 1.5.2:
   «фоновые сообщения по дефолту английские, кроме игроков с явным выбором»).
3. Если игрок не найден (например, удалён) — `None`. Caller сам решает,
   что делать (обычно — пропустить отправку).

Вживую в `LocaleMiddleware` использует тот же резолвер для приоритета
`player.locale_override → tg.language_code → DEFAULT`. Middleware-у
доступен `tg.language_code`, поэтому он сначала смотрит в БД через
этот резолвер, и если override-а нет, фолбэчит на `LocaleResolver`
(стратегию для tg-кода). Так логика «как получается Locale» не
дублируется между middleware-ом и notifier-ом.
"""

from __future__ import annotations

from typing import Protocol

from pipirik_wars.application.i18n.locale import Locale


class IPlayerLocaleResolver(Protocol):
    """Порт «по `tg_id` найти явно выставленный язык игрока».

    Возвращает:
    - `Locale("ru" | "en")`, если игрок зарегистрирован и выставил `/lang`.
    - `None`, если игрок не зарегистрирован ИЛИ не выставлял `/lang`.

    Реализация (`infrastructure.i18n.PlayerLocaleResolverDB`) делает
    SELECT по `users.locale_override` через активный UoW. Тестовые fakes
    (`FakePlayerLocaleResolver`) держат `dict[tg_id, Locale]` в памяти.
    """

    async def resolve_for_tg_id(self, tg_id: int) -> Locale | None: ...


__all__ = ["IPlayerLocaleResolver"]
