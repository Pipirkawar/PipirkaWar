"""bot/handlers package.

`register_routers(dispatcher)` подключает все роутеры в правильном
порядке. На 1.1.C — только `start`.
"""

from aiogram import Dispatcher

from pipirik_wars.bot.handlers.start import router as start_router


def register_routers(dispatcher: Dispatcher) -> None:
    """Подключает все handler-router-ы к dispatcher-у."""
    dispatcher.include_router(start_router)


__all__ = ["register_routers"]
