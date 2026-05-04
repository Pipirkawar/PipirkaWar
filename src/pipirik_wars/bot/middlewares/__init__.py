"""Middleware-стек aiogram (Спринт 1.1.C).

Порядок регистрации (важен — outer first):

1. `ErrorHandlerMiddleware` — ловит исключения всех нижних слоёв.
2. `AuthMiddleware` — кладёт `TgIdentity` в `data`.
3. `LocaleMiddleware` — выбирает локаль (пока всегда `"ru"`).
4. `ThrottleMiddleware` — общий token-bucket rate-limit.

Дальше идёт сам handler. Каждое из этих middleware-ов навешивается на
**оба** observer-а dispatcher-а: `dp.message` и `dp.callback_query`,
плюс на `dp.my_chat_member` (для регистрации клана через бота-в-чате).
"""

from aiogram import Dispatcher

from pipirik_wars.bot.middlewares.auth import AuthMiddleware, TgIdentity
from pipirik_wars.bot.middlewares.error_handler import ErrorHandlerMiddleware
from pipirik_wars.bot.middlewares.locale import LocaleMiddleware
from pipirik_wars.bot.middlewares.throttle import ThrottleMiddleware
from pipirik_wars.infrastructure.rate_limit import IRateLimiter


def register_middlewares(
    dispatcher: Dispatcher,
    *,
    limiter: IRateLimiter,
) -> None:
    """Подключает middleware-стек ко всем нужным observer-ам.

    Вынесено в отдельную функцию, чтобы тесты могли собирать тот же
    стек на test-dispatcher-е без дублирования последовательности.
    """
    error = ErrorHandlerMiddleware()
    auth = AuthMiddleware()
    locale = LocaleMiddleware()
    throttle = ThrottleMiddleware(limiter=limiter)

    for observer in (
        dispatcher.message,
        dispatcher.callback_query,
        dispatcher.my_chat_member,
    ):
        observer.middleware(error)
        observer.middleware(auth)
        observer.middleware(locale)
        observer.middleware(throttle)


__all__ = [
    "AuthMiddleware",
    "ErrorHandlerMiddleware",
    "LocaleMiddleware",
    "TgIdentity",
    "ThrottleMiddleware",
    "register_middlewares",
]
