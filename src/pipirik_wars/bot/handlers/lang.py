"""`/lang` handler (Спринт 1.5.F, ПД 1.5.2).

Команда `/lang ru|en` — выбор языка интерфейса. Только в ЛС:
групповые чаты могут содержать игроков с разными локалями, и
переключение языка для общего чата ничего не значит.

Acceptance из 1.5.F:
- `/lang ru` или `/lang en` — переключает локаль игрока.
- ответ-подтверждение приходит в **новой** локали (например, после
  `/lang en` — на английском).
- Фоновые сообщения (forest-finished от scheduler-а) тоже идут в
  выбранной локали — это работает через `IPlayerLocaleResolver`,
  который запрашивает `users.locale_override` (Спринт 1.5.F).
- Если игрок не зарегистрирован — handler шлёт инструкцию
  «нажми `/start`».

Парсинг аргументов:

`message.text` имеет вид `"/lang"`, `"/lang ru"`, `"/lang en"`,
`"/lang fr"` или `"/lang  ru  "` (пробелы / лишние слова). Берём
первый токен после команды, нормализуем в lowercase и сравниваем со
списком поддерживаемых (`ru`, `en`). Если токена нет — шлём `usage`
helper. Если токен есть, но не из списка — шлём `unsupported` helper.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from pipirik_wars.application.i18n import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    IMessageBundle,
    Locale,
)
from pipirik_wars.application.player import SetPlayerLocale
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.lang import LangPresenter
from pipirik_wars.domain.player import PlayerNotFoundError

router = Router(name="lang")


@router.message(Command("lang"))
async def handle_lang(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    set_player_locale: SetPlayerLocale,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Отвечает на `/lang ru|en` — сохраняет выбор локали игрока."""
    presenter = LangPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    requested = _parse_lang_arg(command.args)
    if requested is None:
        await message.answer(presenter.usage(locale=effective_locale))
        return
    if requested not in SUPPORTED_LOCALES:
        await message.answer(
            presenter.unsupported(locale=effective_locale, code=requested),
        )
        return

    new_locale = Locale(code=requested)
    try:
        await set_player_locale.execute(tg_id=tg_identity.tg_user_id, locale=new_locale)
    except PlayerNotFoundError:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return

    # Подтверждаем в НОВОЙ локали — пользователь только что её выбрал.
    await message.answer(presenter.confirmed(locale=new_locale))


def _parse_lang_arg(raw_args: str | None) -> str | None:
    """Достать первый токен из `/lang <args>`. None, если аргументов нет."""
    if raw_args is None:
        return None
    stripped = raw_args.strip()
    if not stripped:
        return None
    return stripped.split()[0].lower()


__all__ = ["handle_lang", "router"]
