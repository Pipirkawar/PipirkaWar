"""Telegram-нотификаторы рейд-боссов: lobby-close / round-tick / fight-finish (Спринт 3.3-D, D.7).

Реализуют :class:`IBossLobbyCloseNotifier` /
:class:`IBossRoundTickNotifier` / :class:`IBossFightFinishNotifier`
(см. `application/bosses/notifier.py`). Зовутся из APScheduler-callback-ов
(`infrastructure/scheduler/aps.py::_run_boss_lobby_close_job`,
`..._run_boss_round_tick_job`, `..._run_boss_fight_finish_job`) сразу
после успешного `execute(...)`-а соответствующего use-case-а — БД уже
скоммичена, рейд-бой в актуальном состоянии.

В отличие от каравана, у рейд-боя нет clan-чатов: все сообщения шлются
**в личные чаты** живых рейдеров (включая саммонера — он первый рейдер,
ГДД §10.3). Босс по дизайну AFK: о рейде он узнаёт только в момент
финиша — для этого `TelegramBossFightFinishNotifier` отдельно дозванивается
ему в личку, чтобы сообщить об изменении длины (победа рейдеров —
у него отняли длину; поражение рейдеров — он получил +Σ).

Локаль каждого адресата резолвится индивидуально через
`IPlayerLocaleResolver` (фолбэк — `default_locale`, по умолчанию EN, см.
ПД 1.5.2 «фоновые сообщения по дефолту английские»).

Контракт всех трёх нотификаторов:
- зовутся **только** при «новом» исходе (см. `application/bosses/notifier.py`):
  `was_already_closed`/`was_already_finished` → no-op;
- любые ошибки на любом этапе (репо/Telegram/balance/презентер) поглощаются
  и логируются; нотификация — best-effort и НЕ должна валить
  APScheduler-job (job уже сделал свою работу в транзакции).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Final, TypeAlias

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from pipirik_wars.application.bosses import (
    BossFightFinished,
    BossLobbyClosed,
    BossRoundResolved,
    IBossFightFinishNotifier,
    IBossLobbyCloseNotifier,
    IBossRoundTickNotifier,
)
from pipirik_wars.application.i18n import (
    DEFAULT_LOCALE,
    IMessageBundle,
    IPlayerLocaleResolver,
    Locale,
)
from pipirik_wars.bot.presenters.bosses import BossPresenter
from pipirik_wars.domain.balance.config import BossesConfig
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.bosses import (
    BossFight,
    BossParticipant,
    IBossParticipantRepository,
)
from pipirik_wars.domain.player import DisplayName, IPlayerRepository, Player

_LOGGER: Final[logging.Logger] = logging.getLogger("boss_notifier")

# Тип callback-а «дай текст для конкретного рейдера в его локали».
# Используется `_BossNotifierBase._send_to_each_raider`-ом, чтобы каждый
# конкретный нотификатор мог сам решать, какой презентер-метод вызвать,
# а base-класс — только держал общую обвязку (load player + resolve
# locale + send + per-raider error-handling).
_TextForRaiderFn: TypeAlias = Callable[[Player, Locale], str]


class _BossNotifierBase:
    """Общая инфраструктура трёх boss-нотификаторов: репо/locale/presenter/доставка."""

    __slots__ = (
        "_balance",
        "_bot",
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
        players: IPlayerRepository,
        participants: IBossParticipantRepository,
        locale_resolver: IPlayerLocaleResolver | None = None,
        default_locale: Locale = DEFAULT_LOCALE,
        logger: logging.Logger | None = None,
    ) -> None:
        self._bot = bot
        self._presenter = BossPresenter(bundle=bundle)
        self._balance = balance
        self._players = players
        self._participants = participants
        self._locale_resolver = locale_resolver
        self._default_locale = default_locale
        self._logger = logger or _LOGGER

    async def _resolve_locale(self, tg_id: int) -> Locale:
        """Резолв `Locale` для адресата через `IPlayerLocaleResolver`.

        Любые ошибки резолвера поглощаются — фоновые сообщения должны
        быть best-effort и не падать из-за БД-проблем.
        """
        if self._locale_resolver is None:
            return self._default_locale
        try:
            resolved = await self._locale_resolver.resolve_for_tg_id(tg_id)
        except Exception:
            self._logger.exception(
                "boss_notifier: locale resolver failed",
                extra={"tg_id": tg_id},
            )
            return self._default_locale
        return resolved or self._default_locale

    def _display_name_for(self, player: Player) -> DisplayName:
        """`DisplayName` из текущего `IBalanceConfig.get()` (read-only-снимок)."""
        return DisplayName(
            value=self._balance.get().display_name_for(player.length.cm),
        )

    async def _load_player(
        self,
        *,
        player_id: int,
        role: str,
        boss_fight_id: int,
    ) -> Player | None:
        """Загрузить `Player` по доменному id; `None` при отсутствии (логируем)."""
        player = await self._players.get_by_id(player_id=player_id)
        if player is None:
            self._logger.warning(
                "boss_notifier: player not found",
                extra={
                    "player_id": player_id,
                    "role": role,
                    "boss_fight_id": boss_fight_id,
                },
            )
        return player

    async def _send_to_chat(
        self,
        *,
        chat_id: int,
        text: str,
        boss_fight_id: int,
    ) -> None:
        """Best-effort send в личный чат; все ошибки поглощаются и логируются."""
        try:
            await self._bot.send_message(chat_id=chat_id, text=text)
        except TelegramAPIError as exc:
            self._logger.warning(
                "boss_notifier: telegram delivery failed",
                extra={
                    "chat_id": chat_id,
                    "boss_fight_id": boss_fight_id,
                    "error": str(exc),
                },
            )
        except Exception:
            self._logger.exception(
                "boss_notifier: unexpected delivery error",
                extra={"chat_id": chat_id, "boss_fight_id": boss_fight_id},
            )

    async def _send_to_each_raider(
        self,
        *,
        participants: tuple[BossParticipant, ...],
        text_for: _TextForRaiderFn,
        boss_fight_id: int,
    ) -> None:
        """Перебрать рейдеров, отрендерить текст под их локаль и доставить.

        Любая ошибка на одном получателе не блокирует остальных:
        per-raider логируем и идём дальше.
        """
        for participant in participants:
            raider = await self._load_player(
                player_id=participant.player_id,
                role="raider",
                boss_fight_id=boss_fight_id,
            )
            if raider is None:
                continue
            try:
                locale = await self._resolve_locale(raider.tg_id)
                text = text_for(raider, locale)
            except Exception:
                self._logger.exception(
                    "boss_notifier: failed to render text for raider",
                    extra={
                        "boss_fight_id": boss_fight_id,
                        "player_id": participant.player_id,
                        "tg_id": raider.tg_id,
                    },
                )
                continue
            await self._send_to_chat(
                chat_id=raider.tg_id,
                text=text,
                boss_fight_id=boss_fight_id,
            )


class TelegramBossLobbyCloseNotifier(_BossNotifierBase, IBossLobbyCloseNotifier):
    """`IBossLobbyCloseNotifier` через aiogram (Спринт 3.3-D, D.7).

    Шлёт «лобби закрыто, бой начался» в личный чат каждого рейдера
    (включая саммонера). Текст — `BossPresenter.battle_started_text`,
    локаль — индивидуальная (см. `_resolve_locale`).
    """

    async def notify(self, result: BossLobbyClosed) -> None:
        if result.was_already_closed:
            return
        boss_fight = result.boss_fight
        if boss_fight.id is None:
            self._logger.warning(
                "boss_notifier: lobby_close: boss_fight.id is None — skipping",
            )
            return

        prepared = await self._prepare(boss_fight=boss_fight)
        if prepared is None:
            return
        summoner, summoner_display, boss, boss_display, participants, cfg = prepared

        raiders_count = self._presenter.count_alive_raiders(participants)

        def text_for(_raider: Player, locale: Locale) -> str:
            return self._presenter.battle_started_text(
                summoner=summoner,
                summoner_display_name=summoner_display,
                boss=boss,
                boss_display_name=boss_display,
                boss_length_cm=boss_fight.current_boss_length_cm,
                raiders_count=raiders_count,
                cfg=cfg,
                locale=locale,
            )

        await self._send_to_each_raider(
            participants=participants,
            text_for=text_for,
            boss_fight_id=boss_fight.id,
        )

    async def _prepare(
        self,
        *,
        boss_fight: BossFight,
    ) -> (
        tuple[
            Player,
            DisplayName,
            Player,
            DisplayName,
            tuple[BossParticipant, ...],
            BossesConfig,
        ]
        | None
    ):
        """Загрузить участников/саммонера/босса + display_names + cfg.

        Возвращает `None` при любой ошибке загрузки или вычисления
        display_name — тогда `notify(...)` пропускает рассылку.
        """
        assert boss_fight.id is not None
        try:
            participants = await self._participants.list_by_boss_fight(
                boss_fight_id=boss_fight.id,
            )
        except Exception:
            self._logger.exception(
                "boss_notifier: lobby_close: failed to load participants",
                extra={"boss_fight_id": boss_fight.id},
            )
            return None

        summoner = await self._load_player(
            player_id=boss_fight.summoner_player_id,
            role="summoner",
            boss_fight_id=boss_fight.id,
        )
        boss = await self._load_player(
            player_id=boss_fight.boss_player_id,
            role="boss",
            boss_fight_id=boss_fight.id,
        )
        if summoner is None or boss is None:
            return None
        try:
            summoner_display = self._display_name_for(summoner)
            boss_display = self._display_name_for(boss)
            cfg = self._balance.get().bosses
        except Exception:
            self._logger.exception(
                "boss_notifier: lobby_close: failed to compute display_names/cfg",
                extra={"boss_fight_id": boss_fight.id},
            )
            return None
        return summoner, summoner_display, boss, boss_display, participants, cfg


class TelegramBossRoundTickNotifier(_BossNotifierBase, IBossRoundTickNotifier):
    """`IBossRoundTickNotifier` через aiogram (Спринт 3.3-D, D.7).

    Шлёт карточку прошедшего раунда: урон по боссу, выбывшие рейдеры,
    оставшийся HP босса, число живых после раунда. Шлётся только живым
    рейдерам — выбывшие в этом раунде уже удалены из репо.

    Карточка финиш-раунда (`is_finished=True`) тоже шлётся через этот
    нотификатор; финальная раздача наград — отдельным
    `TelegramBossFightFinishNotifier`-ом (его дёргает `FinishBossFight`-job).
    """

    async def notify(self, result: BossRoundResolved) -> None:
        if result.was_already_finished or result.result is None:
            # Идемпотентность + corner-case «alive_raiders=∅ на входе».
            return
        boss_fight = result.boss_fight
        if boss_fight.id is None:
            self._logger.warning(
                "boss_notifier: round_tick: boss_fight.id is None — skipping",
            )
            return

        try:
            participants = await self._participants.list_by_boss_fight(
                boss_fight_id=boss_fight.id,
            )
        except Exception:
            self._logger.exception(
                "boss_notifier: round_tick: failed to load participants",
                extra={"boss_fight_id": boss_fight.id},
            )
            return
        if not participants:
            # Все рейдеры выбыли — финал придёт через FightFinishNotifier.
            return

        boss = await self._load_player(
            player_id=boss_fight.boss_player_id,
            role="boss",
            boss_fight_id=boss_fight.id,
        )
        if boss is None:
            return
        try:
            boss_display = self._display_name_for(boss)
        except Exception:
            self._logger.exception(
                "boss_notifier: round_tick: failed to compute boss display_name",
                extra={"boss_fight_id": boss_fight.id},
            )
            return

        round_number = boss_fight.current_round
        boss_damage_cm = result.result.boss_damage_taken_cm
        eliminated_count = len(result.result.eliminated_player_ids)
        raiders_alive = self._presenter.count_alive_raiders(participants)
        boss_length_cm = boss_fight.current_boss_length_cm

        def text_for(_raider: Player, locale: Locale) -> str:
            return self._presenter.round_tick_text(
                boss=boss,
                boss_display_name=boss_display,
                round_number=round_number,
                boss_damage_cm=boss_damage_cm,
                boss_length_cm=boss_length_cm,
                eliminated_count=eliminated_count,
                raiders_alive=raiders_alive,
                locale=locale,
            )

        await self._send_to_each_raider(
            participants=participants,
            text_for=text_for,
            boss_fight_id=boss_fight.id,
        )


class TelegramBossFightFinishNotifier(_BossNotifierBase, IBossFightFinishNotifier):
    """`IBossFightFinishNotifier` через aiogram (Спринт 3.3-D, D.7).

    Шлёт «бой закончен» в личный чат каждому живому рейдеру (включая
    саммонера) и боссу. Для рейдеров — `battle_finished_victory_text`
    или `battle_finished_defeat_text` в зависимости от `result.raiders_won`.
    Для босса — тот же текст (он узнаёт об исходе впервые: при победе
    рейдеров у него отняли длину, при поражении он получил +Σ).
    """

    async def notify(self, result: BossFightFinished) -> None:
        if result.was_already_finished or result.raiders_won is None:
            return
        boss_fight = result.boss_fight
        if boss_fight.id is None:
            self._logger.warning(
                "boss_notifier: fight_finish: boss_fight.id is None — skipping",
            )
            return

        try:
            participants = await self._participants.list_by_boss_fight(
                boss_fight_id=boss_fight.id,
            )
        except Exception:
            self._logger.exception(
                "boss_notifier: fight_finish: failed to load participants",
                extra={"boss_fight_id": boss_fight.id},
            )
            participants = ()

        summoner = await self._load_player(
            player_id=boss_fight.summoner_player_id,
            role="summoner",
            boss_fight_id=boss_fight.id,
        )
        boss = await self._load_player(
            player_id=boss_fight.boss_player_id,
            role="boss",
            boss_fight_id=boss_fight.id,
        )
        if summoner is None or boss is None:
            return
        try:
            summoner_display = self._display_name_for(summoner)
            boss_display = self._display_name_for(boss)
        except Exception:
            self._logger.exception(
                "boss_notifier: fight_finish: failed to compute display_names",
                extra={"boss_fight_id": boss_fight.id},
            )
            return

        raiders_alive = self._presenter.count_alive_raiders(participants)
        per_raider_grant_cm = (
            (boss_fight.initial_boss_length_cm // raiders_alive) if raiders_alive else 0
        )
        raiders_won = result.raiders_won
        total_granted_cm = result.total_granted_cm

        def text_for_recipient(locale: Locale) -> str:
            if raiders_won:
                return self._presenter.battle_finished_victory_text(
                    summoner=summoner,
                    summoner_display_name=summoner_display,
                    boss=boss,
                    boss_display_name=boss_display,
                    raiders_alive=raiders_alive,
                    per_raider_grant_cm=per_raider_grant_cm,
                    locale=locale,
                )
            return self._presenter.battle_finished_defeat_text(
                summoner=summoner,
                summoner_display_name=summoner_display,
                boss=boss,
                boss_display_name=boss_display,
                raiders_alive=raiders_alive,
                total_granted_cm=total_granted_cm,
                locale=locale,
            )

        # Шлём всем живым рейдерам (саммонер тут же — он первый рейдер
        # пока не выбит; если выбит — в `participants` его нет, но он
        # как summoner_player_id всё равно живой человек, и заслужил
        # увидеть итог).
        await self._send_to_each_raider(
            participants=participants,
            text_for=lambda _raider, locale: text_for_recipient(locale),
            boss_fight_id=boss_fight.id,
        )

        # Если саммонер выбыл из боя в одном из раундов, его уже нет в
        # `participants` — добиваем сообщение отдельно (idempotent: если
        # он остался жив, выше его уже уведомили; повторно НЕ слать —
        # отсюда guard).
        summoner_in_participants = any(
            p.player_id == boss_fight.summoner_player_id for p in participants
        )
        if not summoner_in_participants:
            try:
                summoner_locale = await self._resolve_locale(summoner.tg_id)
                summoner_text = text_for_recipient(summoner_locale)
            except Exception:
                self._logger.exception(
                    "boss_notifier: fight_finish: failed to render summoner text",
                    extra={"boss_fight_id": boss_fight.id},
                )
            else:
                await self._send_to_chat(
                    chat_id=summoner.tg_id,
                    text=summoner_text,
                    boss_fight_id=boss_fight.id,
                )

        # Босс — отдельно: ему «впервые сообщают», что его поучаствовали.
        try:
            boss_locale = await self._resolve_locale(boss.tg_id)
            boss_text = text_for_recipient(boss_locale)
        except Exception:
            self._logger.exception(
                "boss_notifier: fight_finish: failed to render boss text",
                extra={"boss_fight_id": boss_fight.id},
            )
            return
        await self._send_to_chat(
            chat_id=boss.tg_id,
            text=boss_text,
            boss_fight_id=boss_fight.id,
        )


__all__ = [
    "TelegramBossFightFinishNotifier",
    "TelegramBossLobbyCloseNotifier",
    "TelegramBossRoundTickNotifier",
]
