"""Middleware-стек aiogram (Спринт 1.1.C → 2.3.F.1).

Порядок регистрации (важен — outer first):

1. `ErrorHandlerMiddleware` — ловит исключения всех нижних слоёв.
2. `AuthMiddleware` — кладёт `TgIdentity` в `data`.
3. `LocaleMiddleware` — резолвит `Locale` (`ru`/`en`, fallback EN — ПД 1.5.2).
4. `DailyActivityMiddleware` (только `dispatcher.message`, Спринт 2.3.F.1) —
   UPSERT в `daily_active` для preflight-а Главы клана дня. Ставится
   **до** throttle, чтобы rate-limit не гасил запись активности.
5. `ThrottleMiddleware` — общий token-bucket rate-limit.

Дальше идёт сам handler. Каждое из этих middleware-ов навешивается на
**оба** observer-а dispatcher-а: `dp.message` и `dp.callback_query`,
плюс на `dp.my_chat_member` (для регистрации клана через бота-в-чате).
`DailyActivityMiddleware` — исключение: вешается только на `dp.message`,
так как клик inline-кнопки и chat-member-апдейт не должны считаться
«игрок написал в клан-чат».
"""

from aiogram import Dispatcher

from pipirik_wars.application.daily_head import RecordPlayerActivity
from pipirik_wars.application.i18n import IPlayerLocaleResolver, LocaleResolver
from pipirik_wars.bot.middlewares.admin_guard import AdminGuard
from pipirik_wars.bot.middlewares.auth import AuthMiddleware, TgIdentity
from pipirik_wars.bot.middlewares.daily_activity import DailyActivityMiddleware
from pipirik_wars.bot.middlewares.error_handler import ErrorHandlerMiddleware
from pipirik_wars.bot.middlewares.locale import LocaleMiddleware
from pipirik_wars.bot.middlewares.throttle import ThrottleMiddleware
from pipirik_wars.infrastructure.rate_limit import IRateLimiter


def register_middlewares(
    dispatcher: Dispatcher,
    *,
    limiter: IRateLimiter,
    record_player_activity: RecordPlayerActivity | None = None,
    locale_resolver: LocaleResolver | None = None,
    player_locale_resolver: IPlayerLocaleResolver | None = None,
    admin_guard: AdminGuard | None = None,
) -> None:
    """Подключает middleware-стек ко всем нужным observer-ам.

    Вынесено в отдельную функцию, чтобы тесты могли собирать тот же
    стек на test-dispatcher-е без дублирования последовательности.

    `locale_resolver` опциональный — если не передан, используется
    `LocaleResolver()` по дефолту (RU/EN + fallback EN).
    `player_locale_resolver` (Спринт 1.5.F) опциональный: если передан,
    `LocaleMiddleware` сначала спрашивает `users.locale_override` по
    `tg_id` и только если его нет — фолбэчит на `tg.language_code`.
    `record_player_activity` (Спринт 2.3.F.1) опциональный: если
    передан, `DailyActivityMiddleware` подключается к `dp.message`
    и записывает активность в `daily_active` на каждое сообщение
    игрока в групповом чате. Опциональность нужна для unit-тестов
    composition-root и для запуска stand-alone сценариев.

    `admin_guard` (Спринт 2.5-A.2) опциональный: если передан, на все
    три observer-а вешается `AdminGuard` (после `AuthMiddleware`,
    до `LocaleMiddleware`) — он кладёт `data["admin"] = Admin | None`
    для последующих admin-handler-ов. Сам никого не отбрасывает —
    «тихий игнор чужих» делается на уровне admin-router-ов в 2.5-B+.
    """
    error = ErrorHandlerMiddleware()
    auth = AuthMiddleware()
    locale = LocaleMiddleware(
        resolver=locale_resolver,
        player_locale_resolver=player_locale_resolver,
    )
    throttle = ThrottleMiddleware(limiter=limiter)

    for observer in (
        dispatcher.message,
        dispatcher.callback_query,
        dispatcher.my_chat_member,
    ):
        observer.middleware(error)
        observer.middleware(auth)
        if admin_guard is not None:
            observer.middleware(admin_guard)
        observer.middleware(locale)
        observer.middleware(throttle)

    # `DailyActivityMiddleware` — только на сообщения, и встаёт **между**
    # `LocaleMiddleware` и `ThrottleMiddleware`. aiogram применяет
    # middleware в порядке регистрации, поэтому добавляем его в конец
    # (после throttle) — для message-observer-а порядок уже:
    # error → auth → locale → throttle → daily_activity → handler.
    # На самом деле в этом порядке throttle сработает раньше, так что
    # rate-limit-нутый игрок не пройдёт сюда — но это сознательное
    # решение: спам в RPS-лимит не должен заводить активность.
    if record_player_activity is not None:
        dispatcher.message.middleware(
            DailyActivityMiddleware(use_case=record_player_activity),
        )


__all__ = [
    "AdminGuard",
    "AuthMiddleware",
    "DailyActivityMiddleware",
    "ErrorHandlerMiddleware",
    "LocaleMiddleware",
    "TgIdentity",
    "ThrottleMiddleware",
    "register_middlewares",
]
