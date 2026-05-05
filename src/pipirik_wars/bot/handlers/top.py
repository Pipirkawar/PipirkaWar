"""Handler команды `/top` (Спринт 1.4.C → 1.5.C, ПД 1.4.6).

`/top` — публичный read-only запрос: топ-100 игроков по убыванию
длины. Доступен и в ЛС, и в группах (это «социальная» команда —
её цель в групповых чатах одна из основных, ГДД §2.6).

Под капотом use-case `GetTopPlayers` обращается к `ITopPlayersQuery`
(реализация — `TopPlayersCache` с TTL=60s), поэтому даже под пиковой
нагрузкой в БД летит максимум 1 запрос/мин. Регистрация игрока для
`/top` не требуется (это просто чтение публичного рейтинга).

С 1.5.C handler рендерит ответ через `TopPresenter` + `IMessageBundle`,
hardcoded `REPLY_TOP_*_RU`-константы удалены.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.top import GetTopPlayers
from pipirik_wars.bot.presenters.top import TopPresenter

router = Router(name="top")


@router.message(Command("top"))
async def handle_top(
    message: Message,
    get_top_players: GetTopPlayers,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/top` — топ-100 игроков по длине.

    Кэш на стороне use-case-а гарантирует, что массовая «спам-кнопка»
    из чата не нагрузит БД больше одного раза в 60 секунд. Заголовок
    содержит HTML-тег `<b>` — используется глобальный
    `DefaultBotProperties(parse_mode="HTML")`.
    """
    presenter = TopPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    entries = await get_top_players.execute()
    await message.answer(presenter.render(entries, locale=effective_locale))
