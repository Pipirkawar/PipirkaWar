"""Handler команды `/clantop` (Спринт 2.2.A, ПД 2.2.1).

`/clantop` — публичный read-only запрос: топ кланов по сумме длин
активных участников. Доступен и в ЛС, и в группах (это «социальная»
команда, как и `/top`).

Под капотом use-case `GetTopClans` обращается к `IClanTopQuery`
(реализация — `ClanTopCache` с TTL=60s), поэтому даже под пиковой
нагрузкой в БД летит максимум 1 запрос/мин. Регистрация игрока
для `/clantop` не требуется (это просто чтение публичного рейтинга).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.top import GetTopClans
from pipirik_wars.bot.presenters.clantop import ClanTopPresenter

router = Router(name="clantop")


@router.message(Command("clantop"))
async def handle_clantop(
    message: Message,
    get_top_clans: GetTopClans,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/clantop` — топ кланов по сумме длин активных участников.

    Кэш на стороне use-case-а гарантирует, что массовая «спам-кнопка»
    из чата не нагрузит БД больше одного раза в 60 секунд. Заголовок
    содержит HTML-тег `<b>` — используется глобальный
    `DefaultBotProperties(parse_mode="HTML")`.
    """
    presenter = ClanTopPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    entries = await get_top_clans.execute()
    await message.answer(presenter.render(entries, locale=effective_locale))
