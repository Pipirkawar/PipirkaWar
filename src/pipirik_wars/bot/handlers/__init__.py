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
from pipirik_wars.bot.handlers.admin_announcements import (
    router as admin_announcements_router,
)
from pipirik_wars.bot.handlers.admin_audit import router as admin_audit_router
from pipirik_wars.bot.handlers.admin_clan import router as admin_clan_router
from pipirik_wars.bot.handlers.admin_communication import (
    router as admin_communication_router,
)
from pipirik_wars.bot.handlers.admin_economy import router as admin_economy_router
from pipirik_wars.bot.handlers.admin_freeze_payouts import (
    router as admin_freeze_payouts_router,
)
from pipirik_wars.bot.handlers.admin_prize_pool import (
    router as admin_prize_pool_router,
)
from pipirik_wars.bot.handlers.admin_refund_lot import (
    router as admin_refund_lot_router,
)
from pipirik_wars.bot.handlers.admin_setup_totp import router as admin_setup_totp_router
from pipirik_wars.bot.handlers.admin_support import router as admin_support_router
from pipirik_wars.bot.handlers.boss import router as boss_router
from pipirik_wars.bot.handlers.caravan import router as caravan_router
from pipirik_wars.bot.handlers.claim_prize import router as claim_prize_router
from pipirik_wars.bot.handlers.clan_head import router as clan_head_router
from pipirik_wars.bot.handlers.clan_history import router as clan_history_router
from pipirik_wars.bot.handlers.clantop import router as clantop_router
from pipirik_wars.bot.handlers.duel import router as duel_router
from pipirik_wars.bot.handlers.dungeon import router as dungeon_router
from pipirik_wars.bot.handlers.enchant import router as enchant_router
from pipirik_wars.bot.handlers.forest import router as forest_router
from pipirik_wars.bot.handlers.lang import router as lang_router
from pipirik_wars.bot.handlers.link_wallet import router as link_wallet_router
from pipirik_wars.bot.handlers.mass_duel import router as mass_duel_router
from pipirik_wars.bot.handlers.mountains import router as mountains_router
from pipirik_wars.bot.handlers.oracle import router as oracle_router
from pipirik_wars.bot.handlers.profile import router as profile_router
from pipirik_wars.bot.handlers.referral_share import router as referral_share_router
from pipirik_wars.bot.handlers.registration import router as registration_router
from pipirik_wars.bot.handlers.roulette import router as roulette_router
from pipirik_wars.bot.handlers.roulette_paid import router as roulette_paid_router
from pipirik_wars.bot.handlers.start import router as start_router
from pipirik_wars.bot.handlers.top import router as top_router
from pipirik_wars.bot.handlers.upgrade import router as upgrade_router


def register_routers(dispatcher: Dispatcher) -> None:
    """Подключает все handler-router-ы к dispatcher-у."""
    dispatcher.include_router(start_router)
    dispatcher.include_router(profile_router)
    dispatcher.include_router(lang_router)
    # Спринт 4.1-D.6: `/link_wallet` (личка-only) выбор валюты + callback
    # `link_wallet:select:<ton|usdt>` показ инструкций. `/link_wallet_confirm`
    # — backend-вход: парсит `(currency, address, proof)` и зовёт
    # `LinkWallet.execute(...)`. Префикс callback_data — `link_wallet:`.
    dispatcher.include_router(link_wallet_router)
    dispatcher.include_router(forest_router)
    # Спринт 3.1-E: PvE-локации с ±-исходом — `/mountains` и `/dungeon`.
    # Каждый router держит свой префикс callback_data (`mountains:` /
    # `dungeon:`) — пересечения с `forest:` нет.
    dispatcher.include_router(mountains_router)
    dispatcher.include_router(dungeon_router)
    # Спринт 3.2-D: `/caravan` (личка-only) + объявление-в-чат-клана с
    # inline-кнопками лобби. Префикс callback_data — `caravan:`.
    dispatcher.include_router(caravan_router)
    # Спринт 3.3-D: `/boss` (личка-only) + объявление с inline-кнопкой
    # «Показать лобби». Префикс callback_data — `boss:`.
    dispatcher.include_router(boss_router)
    # Спринт 3.4-D: `/enchant <item_id> <scroll_id>` (личка-only) +
    # warning-карточка с inline-кнопками «Подтвердить»/«Отмена».
    # Префикс callback_data — `enc:`. `/inventory` (просмотр items+scrolls)
    # пока выезжает на `inv:`-callback-ах в собственном роутере (D.1b);
    # «Заточить» из карточки `/inventory` (D.1d) подключается отдельным
    # callback-ом и сводится к показу того же warning-а через
    # `EnchantPresenter`.
    dispatcher.include_router(enchant_router)
    # Спринт 3.5-D: `/roulette_free` (личка-only) + spin-callback
    # `roulette_free:spin`. Pre-spin gate (thickness < 2 / length < 100
    # см) показывает warning-карточку без кнопки; при прохождении
    # gate-ов — prompt + инлайн-кнопка «Прокрутить — 100 см». Spin
    # выполняется через `SpinFreeRoulette` с идемпотентностью
    # по `f"msg:{message_id}"` (один клик = один spin).
    dispatcher.include_router(roulette_router)
    # Спринт 4.1-A: `/roulette_paid` (личка-only) + buy-callback-и
    # `roulette_paid:buy_single` / `roulette_paid:buy_pack_10`. Отправляет
    # invoice в Telegram Stars (XTR), валидирует `pre_checkout_query`,
    # проводит spin на `successful_payment`. Spin выполняется через
    # `SpinPaidRoulette` с идемпотентностью по `tg_payment_charge_id`.
    dispatcher.include_router(roulette_paid_router)
    # Спринт 4.1-D.7: `/claim_prize <lot_id>` (личка-only) — забрать
    # зарезервированный CRYPTO_LOT-приз. Префикс callback_data —
    # `claim_prize:`. Callback handler приходит от inline-кнопки
    # «Забрать приз» в результате roulette-спина.
    dispatcher.include_router(claim_prize_router)
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
    # Спринт 2.5-C.6: economy router (`/grant_length`, `/grant_thickness`,
    # `/balance_get`, `/balance_set`). Фильтр `is_admin` — на самом router-е.
    dispatcher.include_router(admin_economy_router)
    # Спринт 2.5-D.4: communication router (`/announce` — broadcast с TOTP).
    # Фильтр `is_admin` — на самом router-е. Импорт модуля выше уже
    # зарегистрировал `dispatch_announce` в `CONFIRM_DISPATCHERS`.
    dispatcher.include_router(admin_communication_router)
    # Спринт 2.5-D.5: read-side observability (`/audit`).
    # Фильтр `is_admin` — на самом router-е.
    dispatcher.include_router(admin_audit_router)
    # Спринт 2.5-D.1+: команды поддержки кланов (`/clan` и далее).
    # Фильтр `is_admin` — на самом router-е.
    dispatcher.include_router(admin_clan_router)
    # Спринт 2.5-D.6: self-service выдача TOTP-секрета (`/admin_setup_totp`).
    # Фильтр `is_admin` — на самом router-е.
    dispatcher.include_router(admin_setup_totp_router)
    # Спринт 4.1-E.12: `/prize_pool` — read-only снимок крипто-пула +
    # freeze-флага (super-admin + audit). Фильтр `is_admin` —
    # на самом router-е; RBAC `SUPER_ADMIN` — на use-case-е.
    dispatcher.include_router(admin_prize_pool_router)
    # Спринт 4.1-E.13: `/refund_lot <lot_id> <reason>` — двухфазный
    # admin-flow (super-admin + TOTP). Импорт модуля выше уже
    # зарегистрировал `dispatch_refund_lot` в `CONFIRM_DISPATCHERS`
    # (фаза 2 использует регистри admin_economy + workflow-data `refund_lot`).
    # Роутер подключается рядом с admin_prize_pool, чтобы admin-RBAC
    # фильтры не оборвались на промежуточных роутерах.
    dispatcher.include_router(admin_refund_lot_router)
    # Спринт 4.1-E.14: `/freeze_payouts <reason>` и `/unfreeze_payouts` —
    # двухфазный admin-flow (super-admin + TOTP). Импорт модуля выше
    # уже зарегистрировал `dispatch_freeze_payouts` и `dispatch_unfreeze_payouts`
    # в `CONFIRM_DISPATCHERS` (фаза 2 использует регистри admin_economy +
    # workflow-data `freeze_payouts` / `unfreeze_payouts`). Роутер подключается
    # рядом с admin_refund_lot из тех же соображений (admin-RBAC chain).
    dispatcher.include_router(admin_freeze_payouts_router)
    # Спринт 4.9: admin-команды канала анонсов (`/announce_weekly`,
    # `/announce_leaderboard`). Фильтр `is_admin` — на самом router-е.
    # Импорт модуля зарегистрировал dispatch-функции в
    # `CONFIRM_DISPATCHERS` (фаза 2 через TOTP).
    dispatcher.include_router(admin_announcements_router)
    dispatcher.include_router(registration_router)


__all__ = ["register_routers"]
