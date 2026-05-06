"""Handler команды `/clan_history` (Спринт 2.2.G / ПД 2.2.5).

`/clan_history` — публичный read-only запрос журнала клановых атак
текущего клана (последние N массовых боёв из `pvp_mass_duels`).
Доступен только в групповом чате клана: атрибут «у клана» в текущей
модели = «у этого Telegram-чата». В ЛС — short-circuit с подсказкой.

Под капотом use-case `GetClanAttackHistory` обращается к
`IClanMassDuelHistoryQuery` (реализация — `SqlAlchemyClanMassDuelHistoryQuery`),
который читает `pvp_mass_duels` с JOIN-ом к `clans` и
коррелированными подзапросами к `pvp_mass_duel_choices` для подсчёта
участников. `IN_PROGRESS`-бои фильтруются на уровне SQL.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.pvp import GetClanAttackHistory
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import ClanHistoryPresenter
from pipirik_wars.domain.clan import IClanRepository

router = Router(name="clan_history")


@router.message(Command("clan_history"))
async def handle_clan_history(
    message: Message,
    tg_identity: TgIdentity | None,
    get_clan_attack_history: GetClanAttackHistory,
    clans: IClanRepository,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/clan_history` — последние N массовых боёв клана этого чата."""
    presenter = ClanHistoryPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    if tg_identity is None:
        return

    chat_kind = tg_identity.chat_kind
    if chat_kind not in ("group", "supergroup"):
        await message.answer(presenter.needs_group_chat(locale=effective_locale))
        return

    clan = await clans.get_by_chat_id(tg_identity.chat_id)
    if clan is None or clan.id is None:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return

    entries = await get_clan_attack_history.execute(clan_id=clan.id)
    await message.answer(
        presenter.render(
            entries,
            clan_title=clan.title.value,
            locale=effective_locale,
        )
    )
