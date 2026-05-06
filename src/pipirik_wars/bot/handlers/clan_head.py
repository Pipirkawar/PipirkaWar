"""Handler команды `/clan_head` (Спринт 2.3.E / ПД 2.3.4-5).

`/clan_head` — публичный button-trigger назначения «Главы клана дня».
Доступен только в групповом чате клана (Telegram chat_id ↔ Clan
устанавливается через `/start`-регистрацию). Идемпотентен:
повторный вызов в те же сутки → «уже назначен» без новых side-effects.

Под капотом use-case `RequestDailyHead` (Спринт 2.3.C) внутри одного
UoW резолвит клан по `chat_id`, проверяет `is_frozen`, зовёт
`DailyHeadService.assign_or_get(...)` (preflight по
`active_member_ids` через `daily_active`-таблицу), сохраняет
`DailyHeadAssignment`, прибавляет `bonus_cm` через `ILengthGranter`,
пишет `audit_log.DAILY_HEAD_ASSIGN`.

Handler рендерит результат: новая запись → праздничный «🎉 поздравляем»
с цитатой из каталога 2.3.D; идемпотентный возврат → тихий «👀 на
сегодня уже назначен».
"""

from __future__ import annotations

import logging
from typing import Final

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.daily_head import IClanQuoteTemplateProvider, RequestDailyHead
from pipirik_wars.application.dto.inputs import RequestDailyHeadInput
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import ClanHeadPresenter
from pipirik_wars.domain.clan import ClanFrozenError, IClanRepository
from pipirik_wars.domain.daily_head import DailyHeadInsufficientActivityError
from pipirik_wars.domain.shared.ports import IRandom

router = Router(name="clan_head")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

_FALLBACK_QUOTE: Final[str] = "👑"


def _head_display(player_first_name: str | None, player_username: str | None) -> str:
    """Имя главы для шаблона `clan-head-success` / `-already-assigned`.

    Берём first_name из Telegram-апдейта (если глава — текущий
    отправитель команды) либо `@username` (если у нас есть только
    `Player.username` из репо). Fallback `"глава"` — крайний случай,
    когда нет ни того ни другого. По факту для button-триггера глава
    может НЕ быть отправителем (`/clan_head` запускает розыгрыш на
    весь клан), поэтому первое поле всегда заполняем `None` и
    отдаём `Player.username`.
    """
    if player_first_name:
        return player_first_name
    if player_username:
        return f"@{player_username}"
    return "глава"


@router.message(Command("clan_head"))
async def handle_clan_head(
    message: Message,
    tg_identity: TgIdentity | None,
    request_daily_head: RequestDailyHead,
    clans: IClanRepository,
    clan_quote_provider: IClanQuoteTemplateProvider,
    pvp_random: IRandom,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/clan_head` — назначить главу клана дня (button-триггер)."""
    presenter = ClanHeadPresenter(bundle=bundle)
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

    try:
        resolved = await request_daily_head.execute(
            RequestDailyHeadInput(
                chat_id=tg_identity.chat_id,
                actor_tg_id=tg_identity.tg_user_id,
            )
        )
    except ClanFrozenError:
        await message.answer(presenter.frozen_clan(locale=effective_locale))
        return
    except DailyHeadInsufficientActivityError as exc:
        await message.answer(
            presenter.not_enough_active(
                locale=effective_locale,
                active_count=exc.active_count,
                required=exc.required,
            )
        )
        return

    quote_text = _pick_quote_text(
        provider=clan_quote_provider,
        random=pvp_random,
        locale=effective_locale,
    )
    head_display = _head_display(
        player_first_name=None,
        player_username=resolved.player.username.value
        if resolved.player and resolved.player.username
        else None,
    )
    rendered_quote = quote_text.replace("{user}", head_display)

    if resolved.was_new and resolved.player is not None:
        await message.answer(
            presenter.success(
                locale=effective_locale,
                head_display_name=head_display,
                bonus_cm=resolved.assignment.bonus_cm,
                new_length_cm=resolved.player.length.cm,
                quote_text=rendered_quote,
            )
        )
    else:
        await message.answer(
            presenter.already_assigned(
                locale=effective_locale,
                head_display_name=head_display,
                bonus_cm=resolved.assignment.bonus_cm,
                quote_text=rendered_quote,
            )
        )


def _pick_quote_text(
    *,
    provider: IClanQuoteTemplateProvider,
    random: IRandom,
    locale: Locale,
) -> str:
    """Случайно выбрать текст цитаты из каталога для данной локали.

    Если каталог пуст (что не должно происходить при корректной
    конфигурации — см. инвариант `IClanQuoteTemplateProvider`),
    возвращаем `_FALLBACK_QUOTE`, чтобы handler никогда не падал
    на рендере.
    """
    templates = provider.get_templates(locale=locale.code)
    if not templates:
        _LOGGER.warning(
            "clan_head_quote_catalog_empty",
            extra={"locale": locale.code},
        )
        return _FALLBACK_QUOTE
    template = random.choice(list(templates))
    return template.text
