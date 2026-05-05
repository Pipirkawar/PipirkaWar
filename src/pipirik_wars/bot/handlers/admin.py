"""Админ-handler-ы (Спринт 1.1.E + 1.2.B).

Команды доступны только в ЛС (групповые админ-команды появятся в
Фазе 4 в виде `/admin_*`, см. ГДД §18.6.5). Авторизация — на стороне
use-case-а: handler ловит `AuthorizationError` и шлёт friendly-текст.

Доступные команды:

- `/balance_reload` (Спринт 1.1.8) — hot-reload `config/balance.yaml`.
- `/admin_stats` (Спринт 1.2.3) — текущий DAU и MAX_DAU.
- `/set_max_dau N` (Спринт 1.2.6) — изменить runtime-лимит DAU.

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
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from pipirik_wars.application.anticheat import LiftAnticheatBan
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.balance import ReloadBalance
from pipirik_wars.application.dau import GetDauStats, SetMaxDau
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.signup_queue import PromoteFromQueue
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.anticheat import AnticheatUnbanPresenter
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.signup_queue import ISignupQueueRepository
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
REPLY_DAU_FORBIDDEN_RU = (
    "❌ У тебя нет прав на эту команду. Управление лимитом DAU доступно "
    "только активным super_admin."
)
REPLY_SET_MAX_DAU_USAGE_RU = (
    "⚠️ Использование: `/set_max_dau N`, где `N` — целое число ≥ 1.\nНапример: `/set_max_dau 1000`."
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


def _format_dau_stats(current: int, max_dau: int, queue_size: int) -> str:
    # paranoia: limit всегда >= 1, но защищаемся от ZeroDivisionError.
    percent = 0 if max_dau <= 0 else round(current * 100 / max_dau)
    return (
        "📊 Статистика бота\n"
        f"• DAU за сегодня: {current} / {max_dau} ({percent}%)\n"
        f"• Очередь регистраций: {queue_size}"
    )


@router.message(Command("admin_stats"))
async def handle_admin_stats(
    message: Message,
    tg_identity: TgIdentity | None,
    get_dau_stats: GetDauStats,
    signup_queue: ISignupQueueRepository,
) -> None:
    """Текущий DAU, MAX_DAU и размер очереди. Только в ЛС.

    Семантически команда «админская», но режим read-only без
    чувствительных данных делает RBAC-гейт избыточным на текущей фазе.
    """
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    stats = await get_dau_stats.execute()
    queue_size = await signup_queue.size()
    await message.answer(_format_dau_stats(stats.current, stats.max_dau, queue_size))


def _parse_set_max_dau(text: str) -> int | None:
    """Распарсить аргумент `/set_max_dau`. None — если формат неверен.

    Поддерживаемые форматы: `/set_max_dau 1000`, `/set_max_dau@PipirikBot 1000`.
    """
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    try:
        value = int(parts[1].strip())
    except ValueError:
        return None
    if value < 1:
        return None
    return value


@router.message(Command("set_max_dau"))
async def handle_set_max_dau(
    message: Message,
    tg_identity: TgIdentity | None,
    set_max_dau: SetMaxDau,
    promote_from_queue: PromoteFromQueue,
) -> None:
    """Изменить runtime-`MAX_DAU` (super_admin only).

    Если лимит вырос — сразу же зовём `PromoteFromQueue.execute()`,
    чтобы поднять из очереди всех, кого влезает по новой ёмкости.
    """
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    text = message.text or ""
    new_value = _parse_set_max_dau(text)
    if new_value is None:
        await message.answer(REPLY_SET_MAX_DAU_USAGE_RU)
        return

    try:
        result = await set_max_dau.execute(
            actor_tg_id=tg_identity.tg_user_id,
            new_max_dau=new_value,
        )
    except AuthorizationError:
        await message.answer(REPLY_DAU_FORBIDDEN_RU)
        return

    promoted_count = 0
    if result.changed and result.new_max_dau > result.previous_max_dau:
        promote_result = await promote_from_queue.execute()
        promoted_count = promote_result.promoted_count

    if result.changed:
        msg = f"✅ MAX_DAU обновлён: {result.previous_max_dau} → {result.new_max_dau}."
        if promoted_count:
            msg += f"\n↑ Из очереди поднято: {promoted_count}."
        await message.answer(msg)
    else:
        await message.answer(f"✅ MAX_DAU не изменён ({result.new_max_dau}) — значение совпало.")


def _parse_anticheat_unban(raw_args: str | None) -> tuple[int, str] | None:
    """Распарсить аргументы `/anticheat_unban <tg_id> <reason>`.

    Возвращает `(tg_id, reason)` или `None`, если формат неверен:
    - меньше двух токенов;
    - первый токен не int или ноль;
    - reason пустой после трима.

    `tg_id` Telegram-а — int (положительный для пользователей,
    отрицательный для каналов; здесь принимаем любой не-ноль).
    """
    if raw_args is None:
        return None
    parts = raw_args.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    try:
        tg_id = int(parts[0])
    except ValueError:
        return None
    reason = parts[1].strip()
    if tg_id == 0 or not reason:
        return None
    return tg_id, reason


@router.message(Command("anticheat_unban"))
async def handle_anticheat_unban(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    lift_anticheat_ban: LiftAnticheatBan,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Снять anti-cheat soft-ban с игрока (Спринт 1.6.G; super_admin only).

    Использование: `/anticheat_unban <tg_id> <reason>`. Reason обязательна,
    идёт в `audit_log` как причина снятия.

    Ответы локализованы (`anticheat-unban-*` в `locales/{ru,en}.ftl`).
    Не из ЛС → стандартный ответ «только в ЛС». Не super_admin →
    `not_authorized`-текст без светки попытки в audit (намеренно).
    """
    presenter = AnticheatUnbanPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    parsed = _parse_anticheat_unban(command.args)
    if parsed is None:
        await message.answer(presenter.usage(locale=effective_locale))
        return
    target_tg_id, reason = parsed

    try:
        result = await lift_anticheat_ban.execute(
            actor_tg_id=tg_identity.tg_user_id,
            target_tg_id=target_tg_id,
            reason=reason,
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return
    except PlayerNotFoundError:
        await message.answer(
            presenter.player_not_found(locale=effective_locale, tg_id=target_tg_id)
        )
        return

    if not result.was_banned:
        await message.answer(presenter.not_banned(locale=effective_locale, tg_id=target_tg_id))
        return

    assert result.banned_until_before is not None
    await message.answer(
        presenter.success(
            locale=effective_locale,
            tg_id=target_tg_id,
            banned_until_before=result.banned_until_before,
            reason=result.reason,
        )
    )
