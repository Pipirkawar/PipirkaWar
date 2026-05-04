"""bot/handlers package.

`register_routers(dispatcher)` подключает все роутеры в правильном
порядке. На 1.1.D — `start` (ЛС, /start → RegisterPlayer) и
`registration` (`my_chat_member`/`chat_member`/`migrate_to` →
RegisterClan/FreezeClan/JoinClan/MigrateClanChatId).
"""

from aiogram import Dispatcher

from pipirik_wars.bot.handlers.registration import router as registration_router
from pipirik_wars.bot.handlers.start import router as start_router


def register_routers(dispatcher: Dispatcher) -> None:
    """Подключает все handler-router-ы к dispatcher-у."""
    dispatcher.include_router(start_router)
    dispatcher.include_router(registration_router)


__all__ = ["register_routers"]
