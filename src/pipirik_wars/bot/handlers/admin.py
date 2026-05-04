"""Админ-handler-ы (Спринт 1.1.E).

Пока — единственная команда `/balance_reload` (Спринт 1.1.8): hot-reload
балансовой конфигурации без рестарта бота.

Команды доступны только в ЛС (групповые админ-команды появятся в
Фазе 4 в виде `/admin_*`, см. ГДД §18.6.5). Авторизация — через
use-case `ReloadBalance`, который сам ходит в `IAdminRepository`
и бросает `AuthorizationError`, если вызов идёт не из-под admin-а с
правом записи в баланс.

Дружелюбные тексты:

- Не из-под админа → handler ловит `AuthorizationError` и шлёт текст
  «недостаточно прав». В audit_log такой случай **не пишется**: use-case
  поднимает ошибку до записи. Это by design — мы не хотим, чтобы
  внешний пользователь мог «засветить» команду, увидев в каком-то
  будущем `/audit`-листинге чужой `tg_id`.
- Невалидный YAML → handler ловит `ConfigError` и шлёт текст «файл
  невалиден, старый снимок остался в силе»; ошибка детально
  логируется через `ErrorHandlerMiddleware` (тот же `structlog`).
- Успех → «версия N → M» (или «версия N» если файл не меняли).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.balance import ReloadBalance
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.shared.errors import ConfigError

router = Router(name="admin")

REPLY_NON_PRIVATE_RU = "🍆 Админ-команды доступны только в ЛС бота."
REPLY_FORBIDDEN_RU = (
    "❌ У тебя нет прав на эту команду. Балансовый reload доступен только "
    "активным super_admin / economist."
)
REPLY_INVALID_CONFIG_RU = (
    "❌ Балансовый файл невалиден — старый снимок остался в силе.\nПодробности — в логах бота."
)


def _format_reloaded(version_before: int, version_after: int) -> str:
    if version_before == version_after:
        return f"✅ Балансовый файл перечитан. Версия не изменилась (v{version_after})."
    return f"✅ Балансовый файл перечитан.\nВерсия: v{version_before} → v{version_after}."


@router.message(Command("balance_reload"))
async def handle_balance_reload(
    message: Message,
    tg_identity: TgIdentity | None,
    reload_balance: ReloadBalance,
) -> None:
    """Hot-reload `config/balance.yaml` (super_admin / economist)."""
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    try:
        result = await reload_balance.execute(actor_tg_id=tg_identity.tg_user_id)
    except AuthorizationError:
        await message.answer(REPLY_FORBIDDEN_RU)
        return
    except ConfigError:
        await message.answer(REPLY_INVALID_CONFIG_RU)
        return

    await message.answer(_format_reloaded(result.version_before, result.version_after))
