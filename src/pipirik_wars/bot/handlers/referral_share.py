"""Handler callback-кнопки «Поделиться» (Спринт 2.4.D-b, ГДД §13.2).

Шарит результат дуэли / похода с реферальной ссылкой в текущий чат.
Callback-data: `ref-share:{kind}:{entity_id}` (kind ∈ {duel, forest}).

Deeplink берётся из `callback.from_user.id` (тот, кто нажал кнопку —
его и реферальная ссылка).
"""

from __future__ import annotations

import logging
from typing import Final

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.referral_share import (
    ReferralSharePresenter,
    ShareKind,
    parse_referral_share_callback_data,
)
from pipirik_wars.domain.forest.repositories import IForestRunRepository
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.pvp import DuelWinner, IDuelRepository

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

router: Final[Router] = Router(name="referral_share")


@router.callback_query(F.data.startswith("ref-share:"))
async def handle_referral_share(
    callback: CallbackQuery,
    bot: Bot,
    tg_identity: TgIdentity | None,
    players: IPlayerRepository,
    duels: IDuelRepository,
    forest_runs: IForestRunRepository,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """«Поделиться» — постит §13.2-сообщение с реферальной ссылкой."""
    if tg_identity is None or callback.data is None:
        return
    effective_locale = locale or DEFAULT_LOCALE
    presenter = ReferralSharePresenter(bundle=bundle)
    sharer_tg_id = tg_identity.tg_user_id

    try:
        parsed = parse_referral_share_callback_data(callback.data)
    except ValueError:
        await callback.answer()
        return

    if parsed.kind is ShareKind.DUEL:
        text = await _share_duel(
            parsed.entity_id,
            sharer_tg_id=sharer_tg_id,
            duels=duels,
            players=players,
            presenter=presenter,
            locale=effective_locale,
        )
    elif parsed.kind is ShareKind.FOREST:
        text = await _share_forest(
            parsed.entity_id,
            sharer_tg_id=sharer_tg_id,
            forest_runs=forest_runs,
            players=players,
            presenter=presenter,
            locale=effective_locale,
        )
    else:  # pragma: no cover
        await callback.answer()
        return

    if text is None:
        await callback.answer()
        return

    chat_id = callback.message.chat.id if callback.message is not None else tg_identity.chat_id
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        _LOGGER.warning(
            "referral_share: failed to post",
            extra={"kind": parsed.kind.value, "entity_id": parsed.entity_id, "chat_id": chat_id},
        )
    await callback.answer()


async def _share_duel(
    duel_id: int,
    *,
    sharer_tg_id: int,
    duels: IDuelRepository,
    players: IPlayerRepository,
    presenter: ReferralSharePresenter,
    locale: Locale,
) -> str | None:
    duel = await duels.get_by_id(duel_id=duel_id)
    if duel is None or duel.final_outcome is None or duel.challenged_id is None:
        return None

    p1 = await players.get_by_id(player_id=duel.challenger_id)
    p2 = await players.get_by_id(player_id=duel.challenged_id)
    p1_name = _format_username(p1.username.value if p1 and p1.username else None)
    p2_name = _format_username(p2.username.value if p2 and p2.username else None)

    outcome = duel.final_outcome
    if outcome.winner is DuelWinner.DRAW:
        return presenter.share_text_duel_draw(
            p1_name=p1_name,
            p2_name=p2_name,
            sharer_tg_id=sharer_tg_id,
            locale=locale,
        )

    if outcome.winner is DuelWinner.P1:
        winner_name = p1_name
        loser_name = p2_name
        delta_cm = outcome.p1_delta_cm
        winner_player = p1
    else:
        winner_name = p2_name
        loser_name = p1_name
        delta_cm = outcome.p2_delta_cm
        winner_player = p2

    winner_length_cm = winner_player.length.cm if winner_player else 0

    return presenter.share_text_duel_victory(
        winner_name=winner_name,
        loser_name=loser_name,
        delta_cm=delta_cm,
        winner_length_cm=winner_length_cm,
        sharer_tg_id=sharer_tg_id,
        locale=locale,
    )


async def _share_forest(
    run_id: int,
    *,
    sharer_tg_id: int,
    forest_runs: IForestRunRepository,
    players: IPlayerRepository,
    presenter: ReferralSharePresenter,
    locale: Locale,
) -> str | None:
    run = await forest_runs.get_by_id(run_id=run_id)
    if run is None:
        return None
    player = await players.get_by_id(player_id=run.player_id)
    if player is None:
        return None

    player_name = _format_username(player.username.value if player.username else None)
    return presenter.share_text_forest(
        player_name=player_name,
        delta_cm=run.length_delta_cm,
        length_cm=player.length.cm,
        sharer_tg_id=sharer_tg_id,
        locale=locale,
    )


def _format_username(username: str | None) -> str:
    if username is None or not username.strip():
        return "—"
    return f"@{username}"


__all__ = ["router"]
