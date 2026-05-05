"""Handler команды `/top` (Спринт 1.4.C, ПД 1.4.6).

`/top` — публичный read-only запрос: топ-100 игроков по убыванию
длины. Доступен и в ЛС, и в группах (это «социальная» команда —
её цель в групповых чатах одна из основных, ГДД §2.6).

Под капотом use-case `GetTopPlayers` обращается к `ITopPlayersQuery`
(реализация — `TopPlayersCache` с TTL=60s), поэтому даже под пиковой
нагрузкой в БД летит максимум 1 запрос/мин. Регистрация игрока для
`/top` не требуется (это просто чтение публичного рейтинга).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.top import GetTopPlayers
from pipirik_wars.bot.presenters import render_top

router = Router(name="top")


@router.message(Command("top"))
async def handle_top(
    message: Message,
    get_top_players: GetTopPlayers,
) -> None:
    """`/top` — топ-100 игроков по длине.

    Кэш на стороне use-case-а гарантирует, что массовая «спам-кнопка»
    из чата не нагрузит БД больше одного раза в 60 секунд. Заголовок
    содержит HTML-тег `<b>` — используется глобальный
    `DefaultBotProperties(parse_mode="HTML")`.
    """
    entries = await get_top_players.execute()
    await message.answer(render_top(entries))
