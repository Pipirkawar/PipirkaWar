"""bot/handlers package.

`register_routers(dispatcher)` подключает все роутеры в правильном
порядке. На 1.1.E — `start` (ЛС, /start → RegisterPlayer),
`registration` (`my_chat_member`/`chat_member`/`migrate_to` →
RegisterClan/FreezeClan/JoinClan/MigrateClanChatId), `profile`
(/profile → GetProfile + рендер карточки) и `admin`
(/balance_reload → ReloadBalance, super_admin/economist).
"""

from aiogram import Dispatcher

from pipirik_wars.bot.handlers.admin import router as admin_router
from pipirik_wars.bot.handlers.profile import router as profile_router
from pipirik_wars.bot.handlers.registration import router as registration_router
from pipirik_wars.bot.handlers.start import router as start_router


def register_routers(dispatcher: Dispatcher) -> None:
    """Подключает все handler-router-ы к dispatcher-у."""
    dispatcher.include_router(start_router)
    dispatcher.include_router(profile_router)
    dispatcher.include_router(admin_router)
    dispatcher.include_router(registration_router)


__all__ = ["register_routers"]
