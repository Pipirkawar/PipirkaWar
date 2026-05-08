"""Telegram-нотификаторы старта/финиша боя каравана (Спринт 3.2-D, D.6).

Реализуют :class:`ICaravanLobbyCloseNotifier` и
:class:`ICaravanBattleFinishNotifier`. Зовутся из APScheduler-callback-ов
(`infrastructure/scheduler/aps.py::_run_caravan_lobby_close_job`,
`..._run_caravan_battle_finish_job`) сразу после успешного `execute(...)`
use-case-а, который применил доменные изменения внутри транзакции.

Контракт обоих нотификаторов:

* зовутся **только** при «новом» исходе (см. `application/caravans/notifier.py`);
* загружают sender/receiver кланы (`IClanRepository`), лидера и
  Атамана (`IPlayerRepository`), участников каравана
  (`ICaravanParticipantRepository`), резолвят локаль лидера через
  опциональный `IPlayerLocaleResolver` (fallback — `default_locale`),
  рендерят текст через :class:`CaravanPresenter` и шлют в чаты обоих
  кланов через `aiogram.Bot.send_message`;
* любые ошибки на любом этапе (репо/Telegram/balance) поглощаются и
  логируются — нотификация best-effort, она НЕ должна валить
  APScheduler-job (job уже сделал свою работу в транзакции).
"""

from __future__ import annotations

import logging
from typing import Final

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from pipirik_wars.application.caravans import (
    CaravanBattleFinished,
    ClosedCaravanLobby,
    ICaravanBattleFinishNotifier,
    ICaravanLobbyCloseNotifier,
)
from pipirik_wars.application.i18n import (
    DEFAULT_LOCALE,
    IMessageBundle,
    IPlayerLocaleResolver,
    Locale,
)
from pipirik_wars.bot.presenters.caravans import CaravanPresenter
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.caravan import (
    CaravanParticipant,
    CaravanRole,
    ICaravanParticipantRepository,
)
from pipirik_wars.domain.caravan.services import (
    CaravanBattleResult,
    CaravanParticipantOutcome,
)
from pipirik_wars.domain.clan import Clan, IClanRepository
from pipirik_wars.domain.player import DisplayName, IPlayerRepository, Player

_LOGGER: Final[logging.Logger] = logging.getLogger("caravan_notifier")


class _CaravanNotifierBase:
    """Общая инфраструктура (репо/locale/presenter) для двух caravan-нотификаторов."""

    __slots__ = (
        "_balance",
        "_bot",
        "_clans",
        "_default_locale",
        "_locale_resolver",
        "_logger",
        "_participants",
        "_players",
        "_presenter",
    )

    def __init__(
        self,
        *,
        bot: Bot,
        bundle: IMessageBundle,
        balance: IBalanceConfig,
        clans: IClanRepository,
        players: IPlayerRepository,
        participants: ICaravanParticipantRepository,
        locale_resolver: IPlayerLocaleResolver | None = None,
        default_locale: Locale = DEFAULT_LOCALE,
        logger: logging.Logger | None = None,
    ) -> None:
        self._bot = bot
        self._presenter = CaravanPresenter(bundle=bundle)
        self._balance = balance
        self._clans = clans
        self._players = players
        self._participants = participants
        self._locale_resolver = locale_resolver
        self._default_locale = default_locale
        self._logger = logger or _LOGGER

    async def _resolve_locale(self, tg_id: int) -> Locale:
        if self._locale_resolver is None:
            return self._default_locale
        try:
            resolved = await self._locale_resolver.resolve_for_tg_id(tg_id)
        except Exception:
            self._logger.exception(
                "caravan_notifier: locale resolver failed",
                extra={"tg_id": tg_id},
            )
            return self._default_locale
        return resolved or self._default_locale

    def _display_name_for(self, player: Player) -> DisplayName:
        return DisplayName(
            value=self._balance.get().display_name_for(player.length.cm),
        )

    async def _load_clans(
        self,
        *,
        sender_clan_id: int,
        receiver_clan_id: int,
    ) -> tuple[Clan, Clan] | None:
        sender_clan = await self._clans.get_by_id(sender_clan_id)
        receiver_clan = await self._clans.get_by_id(receiver_clan_id)
        if sender_clan is None or receiver_clan is None:
            self._logger.warning(
                "caravan_notifier: clan(s) missing",
                extra={
                    "sender_clan_id": sender_clan_id,
                    "receiver_clan_id": receiver_clan_id,
                    "sender_found": sender_clan is not None,
                    "receiver_found": receiver_clan is not None,
                },
            )
            return None
        return sender_clan, receiver_clan

    async def _load_leader(self, *, leader_player_id: int) -> Player | None:
        leader = await self._players.get_by_id(player_id=leader_player_id)
        if leader is None:
            self._logger.warning(
                "caravan_notifier: leader player not found",
                extra={"leader_player_id": leader_player_id},
            )
        return leader

    async def _send_to_chat(self, *, chat_id: int, text: str, caravan_id: int) -> None:
        try:
            await self._bot.send_message(chat_id=chat_id, text=text)
        except TelegramAPIError as exc:
            self._logger.warning(
                "caravan_notifier: telegram delivery failed",
                extra={
                    "chat_id": chat_id,
                    "caravan_id": caravan_id,
                    "error": str(exc),
                },
            )
        except Exception:
            self._logger.exception(
                "caravan_notifier: unexpected delivery error",
                extra={"chat_id": chat_id, "caravan_id": caravan_id},
            )


class TelegramCaravanLobbyCloseNotifier(_CaravanNotifierBase, ICaravanLobbyCloseNotifier):
    """`ICaravanLobbyCloseNotifier` через aiogram (Спринт 3.2-D, D.6)."""

    async def notify(self, result: ClosedCaravanLobby) -> None:
        prepared = await self._prepare(result)
        if prepared is None:
            return
        text, sender_clan, receiver_clan, caravan_id = prepared
        await self._send_to_chat(chat_id=sender_clan.chat_id, text=text, caravan_id=caravan_id)
        await self._send_to_chat(chat_id=receiver_clan.chat_id, text=text, caravan_id=caravan_id)

    async def _prepare(self, result: ClosedCaravanLobby) -> tuple[str, Clan, Clan, int] | None:
        """Подготовить текст и чаты для рассылки.

        Возвращает `None`, если хоть один шаг (загрузка кланов / лидера /
        участников / рендер текста) упал — в этом случае на стороне
        `notify(...)` посылка пропускается. Все ошибки логируются.
        """
        if result.was_already_closed:
            # Идемпотентность: повторный close-job (race / replace_existing)
            # не спамит чаты.
            return None
        caravan = result.caravan
        if caravan.id is None:
            self._logger.warning("caravan_notifier: lobby_close: caravan.id is None — skipping")
            return None
        clans = await self._load_clans(
            sender_clan_id=caravan.sender_clan_id,
            receiver_clan_id=caravan.receiver_clan_id,
        )
        if clans is None:
            return None
        sender_clan, receiver_clan = clans
        leader = await self._load_leader(leader_player_id=caravan.leader_player_id)
        if leader is None:
            return None
        try:
            participants = await self._participants.list_by_caravan(
                caravan_id=caravan.id,
            )
            leader_display_name = self._display_name_for(leader)
            locale = await self._resolve_locale(leader.tg_id)
            cfg = self._balance.get().caravans
            text = self._presenter.battle_started_text(
                caravan=caravan,
                participants=participants,
                leader=leader,
                leader_display_name=leader_display_name,
                sender_clan_name=sender_clan.title.value,
                receiver_clan_name=receiver_clan.title.value,
                cfg=cfg,
                locale=locale,
            )
        except Exception:
            self._logger.exception(
                "caravan_notifier: lobby_close: failed to prepare message",
                extra={"caravan_id": caravan.id},
            )
            return None
        return text, sender_clan, receiver_clan, caravan.id


class TelegramCaravanBattleFinishNotifier(_CaravanNotifierBase, ICaravanBattleFinishNotifier):
    """`ICaravanBattleFinishNotifier` через aiogram (Спринт 3.2-D, D.6)."""

    async def notify(self, result: CaravanBattleFinished) -> None:
        prepared = await self._prepare(result)
        if prepared is None:
            return
        text, sender_clan, receiver_clan, caravan_id = prepared
        await self._send_to_chat(chat_id=sender_clan.chat_id, text=text, caravan_id=caravan_id)
        await self._send_to_chat(chat_id=receiver_clan.chat_id, text=text, caravan_id=caravan_id)

    async def _prepare(self, result: CaravanBattleFinished) -> tuple[str, Clan, Clan, int] | None:
        """Подготовить текст и чаты для рассылки.

        Возвращает `None`, если шаг подготовки упал. Логирует все
        ошибки, не пробрасывает их.
        """
        if result.was_already_finished or result.result is None:
            # Идемпотентность + no-op путь use-case-а.
            return None
        caravan = result.caravan
        if caravan.id is None:
            self._logger.warning("caravan_notifier: battle_finish: caravan.id is None — skipping")
            return None
        clans = await self._load_clans(
            sender_clan_id=caravan.sender_clan_id,
            receiver_clan_id=caravan.receiver_clan_id,
        )
        if clans is None:
            return None
        sender_clan, receiver_clan = clans
        leader = await self._load_leader(leader_player_id=caravan.leader_player_id)
        if leader is None:
            return None
        battle_result = result.result
        try:
            leader_display_name = self._display_name_for(leader)
            locale = await self._resolve_locale(leader.tg_id)
            text = await self._render_text(
                battle_result=battle_result,
                leader=leader,
                leader_display_name=leader_display_name,
                sender_clan=sender_clan,
                receiver_clan=receiver_clan,
                caravan_id=caravan.id,
                locale=locale,
            )
        except Exception:
            self._logger.exception(
                "caravan_notifier: battle_finish: failed to prepare message",
                extra={"caravan_id": caravan.id, "raiders_won": battle_result.raiders_won},
            )
            return None
        return text, sender_clan, receiver_clan, caravan.id

    async def _render_text(
        self,
        *,
        battle_result: CaravanBattleResult,
        leader: Player,
        leader_display_name: DisplayName,
        sender_clan: Clan,
        receiver_clan: Clan,
        caravan_id: int,
        locale: Locale,
    ) -> str:
        if battle_result.raiders_won:
            ataman, ataman_display_name = await self._resolve_ataman(
                outcomes=battle_result.participant_outcomes,
                caravan_id=caravan_id,
            )
            return self._presenter.battle_finished_raided_text(
                result=battle_result,
                leader=leader,
                leader_display_name=leader_display_name,
                sender_clan_name=sender_clan.title.value,
                receiver_clan_name=receiver_clan.title.value,
                ataman=ataman,
                ataman_display_name=ataman_display_name,
                locale=locale,
            )
        return self._presenter.battle_finished_delivered_text(
            result=battle_result,
            leader=leader,
            leader_display_name=leader_display_name,
            sender_clan_name=sender_clan.title.value,
            receiver_clan_name=receiver_clan.title.value,
            locale=locale,
        )

    async def _resolve_ataman(
        self,
        *,
        outcomes: tuple[CaravanParticipantOutcome, ...],
        caravan_id: int,
    ) -> tuple[Player | None, DisplayName | None]:
        """Найти участника-Атамана среди outcome-ов и загрузить его игрока.

        Если во входящих outcome-ах нет `gets_ataman_title=True`
        (вырожденный случай — `raiders_won=True` без рейдеров) — вернёт
        `(None, None)` и презентер отрендерит прочерк.
        """
        ataman_outcome: CaravanParticipant | None = None
        for outcome in outcomes:
            if outcome.gets_ataman_title and outcome.participant.role is CaravanRole.RAIDER:
                ataman_outcome = outcome.participant
                break
        if ataman_outcome is None:
            return None, None
        ataman = await self._players.get_by_id(player_id=ataman_outcome.player_id)
        if ataman is None:
            self._logger.warning(
                "caravan_notifier: battle_finish: ataman player not found",
                extra={
                    "caravan_id": caravan_id,
                    "ataman_player_id": ataman_outcome.player_id,
                },
            )
            return None, None
        try:
            ataman_display_name = self._display_name_for(ataman)
        except Exception:
            self._logger.exception(
                "caravan_notifier: battle_finish: failed to compute ataman display_name",
                extra={
                    "caravan_id": caravan_id,
                    "ataman_player_id": ataman_outcome.player_id,
                },
            )
            return None, None
        return ataman, ataman_display_name


__all__ = [
    "TelegramCaravanBattleFinishNotifier",
    "TelegramCaravanLobbyCloseNotifier",
]
