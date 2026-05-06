"""bot/handlers package.

`register_routers(dispatcher)` подключает все роутеры в правильном
порядке. На 1.4.C — `start` (ЛС, /start → RegisterPlayer),
`registration` (`my_chat_member`/`chat_member`/`migrate_to` →
RegisterClan/FreezeClan/JoinClan/MigrateClanChatId), `profile`
(/profile → GetProfile + рендер карточки), `admin`
(/balance_reload → ReloadBalance, super_admin/economist), `forest`
(/forest → StartForestRun + callback-кнопки результата леса),
`upgrade` (Спринт 1.4.A: /upgrade → UpgradeThickness +
callback-подтверждение), `oracle` (Спринт 1.4.B: /oracle →
InvokeOracle) и `top` (Спринт 1.4.C: /top → GetTopPlayers с TTL-кэшем).
"""

from aiogram import Dispatcher

from pipirik_wars.bot.handlers.admin import router as admin_router
from pipirik_wars.bot.handlers.admin_support import router as admin_support_router
from pipirik_wars.bot.handlers.clan_head import router as clan_head_router
from pipirik_wars.bot.handlers.clan_history import router as clan_history_router
from pipirik_wars.bot.handlers.clantop import router as clantop_router
from pipirik_wars.bot.handlers.duel import router as duel_router
from pipirik_wars.bot.handlers.forest import router as forest_router
from pipirik_wars.bot.handlers.lang import router as lang_router
from pipirik_wars.bot.handlers.mass_duel import router as mass_duel_router
from pipirik_wars.bot.handlers.oracle import router as oracle_router
from pipirik_wars.bot.handlers.profile import router as profile_router
from pipirik_wars.bot.handlers.referral_share import router as referral_share_router
from pipirik_wars.bot.handlers.registration import router as registration_router
from pipirik_wars.bot.handlers.start import router as start_router
from pipirik_wars.bot.handlers.top import router as top_router
from pipirik_wars.bot.handlers.upgrade import router as upgrade_router


def register_routers(dispatcher: Dispatcher) -> None:
    """Подключает все handler-router-ы к dispatcher-у."""
    dispatcher.include_router(start_router)
    dispatcher.include_router(profile_router)
    dispatcher.include_router(lang_router)
    dispatcher.include_router(forest_router)
    dispatcher.include_router(upgrade_router)
    dispatcher.include_router(duel_router)
    dispatcher.include_router(mass_duel_router)
    dispatcher.include_router(referral_share_router)
    dispatcher.include_router(oracle_router)
    dispatcher.include_router(top_router)
    dispatcher.include_router(clantop_router)
    dispatcher.include_router(clan_head_router)
    dispatcher.include_router(clan_history_router)
    dispatcher.include_router(admin_router)
    # Спринт 2.5-B.6: extended-support router (`/find_player`, `/player`,
    # `/freeze`, `/unfreeze`, `/ban`, `/confirm`). Фильтр `is_admin` живёт
    # на самом router-е (см. `admin_support.router.message.filter(...)`),
    # поэтому здесь — обычный `include_router`.
    dispatcher.include_router(admin_support_router)
    dispatcher.include_router(registration_router)


__all__ = ["register_routers"]
