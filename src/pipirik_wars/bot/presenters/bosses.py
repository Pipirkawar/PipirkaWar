"""Презентер `/boss`-ветки (Спринт 3.3-D, ГДД §10).

Отвечает за все локализованные сообщения handler-а `/boss`:
ответ-инструкции (незарегистрированный игрок, кулдаун, gate по
толщине / длине, заморозка), сообщения об успехе (подтверждение
саммонеру в личке + объявление в чате), карточку лобби с inline-
кнопками, callback-toast-ы для join / leave / cancel, а также
тексты уведомлений из APScheduler-callback-ов (старт боя, тик
раунда, финиш боя). Вся i18n идёт через `IMessageBundle` —
handler никогда не клеит строки сам.

Сериализация `callback_data` для inline-кнопок (`boss:<action>:<id>`)
— отдельный free-form helper в этом же модуле; держим её рядом с
презентером по тому же паттерну, что у каравана / forest / mountains
/ dungeon (одна точка истины для префикса `boss:` и форматов
событий).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.bot.presenters.profile import title_message_key
from pipirik_wars.domain.balance.config import BossesConfig
from pipirik_wars.domain.bosses import BossFight, BossParticipant
from pipirik_wars.domain.player import DisplayName, Player, PlayerName, Title

_BOSS_CALLBACK_PREFIX: Final[str] = "boss"

BossCallbackAction = Literal[
    "show_lobby",
    "join",
    "leave",
    "cancel",
]
_VALID_ACTIONS: Final[frozenset[BossCallbackAction]] = frozenset(
    {
        "show_lobby",
        "join",
        "leave",
        "cancel",
    },
)


@dataclass(frozen=True, slots=True)
class BossCallbackData:
    """Распаршенный `callback_data` инлайн-кнопки рейд-босса.

    `boss:<action>:<boss_fight_id>`. Поддерживаемые `action`-ы:

    - `show_lobby` — открыть карточку лобби (под объявлением в чате,
      где был вызван `/boss`);
    - `join` — вступить в лобби рейдером;
    - `leave` — выйти из лобби (для не-саммонера);
    - `cancel` — отменить рейд (только саммонер).
    """

    action: BossCallbackAction
    boss_fight_id: int


def boss_callback_data(*, action: BossCallbackAction, boss_fight_id: int) -> str:
    """Сериализовать `callback_data` инлайн-кнопки рейд-босса.

    Формат: `boss:<action>:<boss_fight_id>`. Telegram callback_data
    — 64 байт жёстко; `boss_fight_id` до 19 знаков и `action` до 16
    символов укладываемся с большим запасом.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown boss callback action: {action!r}")
    if boss_fight_id <= 0:
        raise ValueError(f"boss_fight_id must be > 0, got {boss_fight_id}")
    return f"{_BOSS_CALLBACK_PREFIX}:{action}:{boss_fight_id}"


def parse_boss_callback_data(data: str) -> BossCallbackData:
    """Распарсить `callback_data` рейд-босса. На любой мусор — `ValueError`."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != _BOSS_CALLBACK_PREFIX:
        raise ValueError(f"boss callback_data must be 'boss:<action>:<id>', got {data!r}")
    _, action_raw, boss_fight_id_raw = parts
    action: BossCallbackAction
    if action_raw == "show_lobby":
        action = "show_lobby"
    elif action_raw == "join":
        action = "join"
    elif action_raw == "leave":
        action = "leave"
    elif action_raw == "cancel":
        action = "cancel"
    else:
        raise ValueError(f"unknown boss action: {action_raw!r}")
    try:
        boss_fight_id = int(boss_fight_id_raw)
    except ValueError as exc:
        raise ValueError(f"boss_fight_id must be int, got {boss_fight_id_raw!r}") from exc
    if boss_fight_id <= 0:
        raise ValueError(f"boss_fight_id must be > 0, got {boss_fight_id}")
    return BossCallbackData(action=action, boss_fight_id=boss_fight_id)


def is_boss_callback(data: str | None) -> bool:
    """Filter helper — это callback рейд-босса?

    Используется handler-ом через `F.data.startswith(...)`-фильтр,
    чтобы не пересекаться с forest / mountains / dungeon / caravan.
    """
    if data is None:
        return False
    return data.startswith(f"{_BOSS_CALLBACK_PREFIX}:")


class BossPresenter:
    """Локализованный рендер ответов `/boss`-handler-а через `IMessageBundle`.

    Использует префикс ключей `bosses-*` (множественное число —
    исторический выбор файла локалей: рейд-боссы как игровая механика).
    """

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- Команда `/boss` — где её пускать / парсинг ---

    def not_registered(self, *, locale: Locale) -> str:
        """`PlayerNotFoundError` — игрок не нажимал /start."""
        return self._bundle.format(MessageKey("bosses-not-registered"), locale=locale)

    def usage(self, *, top_n_pool: int, locale: Locale) -> str:
        """Игрок вызвал `/boss` с лишними аргументами.

        Подсказка: команда без аргументов, босс берётся случайно из
        топ-`top_n_pool` (ГДД §10.1: «случайный из топ-30»).
        """
        return self._bundle.format(
            MessageKey("bosses-usage"),
            locale=locale,
            top_n_pool=top_n_pool,
        )

    # --- Команда `/boss` — отказы по правилам и состоянию ---

    def cooldown(self, *, remaining_seconds: int, locale: Locale) -> str:
        """Глобальный 4-часовой кулдаун рейд-босса (`BossSummonOnGlobalCooldownError`)."""
        # Округляем вверх до минут — ниже минуты UX-смысла нет.
        remaining_minutes = max(1, (remaining_seconds + 59) // 60)
        return self._bundle.format(
            MessageKey("bosses-cooldown"),
            locale=locale,
            remaining_minutes=remaining_minutes,
        )

    def already_in(self, *, locale: Locale) -> str:
        """Игрок уже участвует в активном рейде (`AlreadyInBossFightError`)."""
        return self._bundle.format(MessageKey("bosses-already-in"), locale=locale)

    def requirement_thickness(self, *, required: int, actual: int, locale: Locale) -> str:
        """Толщина < `min_thickness_level_summoner` (ГДД §10.1 = 9)."""
        return self._bundle.format(
            MessageKey("bosses-requirement-thickness"),
            locale=locale,
            required=required,
            actual=actual,
        )

    def requirement_length(self, *, required_cm: int, actual_cm: int, locale: Locale) -> str:
        """`length.cm < bosses.min_length_cm` (ГДД §10.1 = 20 см)."""
        return self._bundle.format(
            MessageKey("bosses-requirement-length"),
            locale=locale,
            required_cm=required_cm,
            actual_cm=actual_cm,
        )

    def player_frozen(self, *, locale: Locale) -> str:
        """Игрок `FROZEN`/`BANNED` (DAU-gate)."""
        return self._bundle.format(MessageKey("bosses-player-frozen"), locale=locale)

    def pool_empty(self, *, locale: Locale) -> str:
        """Пул кандидатов в боссы пуст (`BossPlayerPoolEmptyError`)."""
        return self._bundle.format(MessageKey("bosses-pool-empty"), locale=locale)

    # --- Команда `/boss` — успех ---

    def summoned_private(
        self,
        *,
        boss: Player,
        boss_display_name: DisplayName,
        boss_length_cm: int,
        lobby_minutes: int,
        locale: Locale,
    ) -> str:
        """Подтверждение саммонеру в личке: рейд-босс призван."""
        boss_nick = self._render_full_nick(
            title=boss.title,
            display_name=boss_display_name,
            name=boss.name,
            locale=locale,
        )
        return self._bundle.format(
            MessageKey("bosses-summoned-private"),
            locale=locale,
            boss_nick=boss_nick,
            boss_length_cm=boss_length_cm,
            lobby_minutes=lobby_minutes,
        )

    def summoned_announcement(
        self,
        *,
        summoner: Player,
        summoner_display_name: DisplayName,
        boss: Player,
        boss_display_name: DisplayName,
        boss_length_cm: int,
        lobby_minutes: int,
        locale: Locale,
    ) -> str:
        """Объявление в чате: саммонер бросает вызов боссу."""
        summoner_nick = self._render_full_nick(
            title=summoner.title,
            display_name=summoner_display_name,
            name=summoner.name,
            locale=locale,
        )
        boss_nick = self._render_full_nick(
            title=boss.title,
            display_name=boss_display_name,
            name=boss.name,
            locale=locale,
        )
        return self._bundle.format(
            MessageKey("bosses-summoned-announcement"),
            locale=locale,
            summoner_nick=summoner_nick,
            boss_nick=boss_nick,
            boss_length_cm=boss_length_cm,
            lobby_minutes=lobby_minutes,
        )

    def announcement_keyboard(
        self,
        *,
        boss_fight_id: int,
        locale: Locale,
    ) -> InlineKeyboardMarkup:
        """Inline-клавиатура под объявлением: единственная кнопка
        «Показать лобби» (full lobby UI открывается callback-ом).
        """
        button = InlineKeyboardButton(
            text=self._bundle.format(MessageKey("bosses-button-show-lobby"), locale=locale),
            callback_data=boss_callback_data(
                action="show_lobby",
                boss_fight_id=boss_fight_id,
            ),
        )
        return InlineKeyboardMarkup(inline_keyboard=[[button]])

    # --- Callback `boss:show_lobby:<id>` ---

    def lobby_state_text(
        self,
        *,
        boss_fight: BossFight,
        raiders_count: int,
        summoner: Player,
        summoner_display_name: DisplayName,
        boss: Player,
        boss_display_name: DisplayName,
        now: datetime,
        locale: Locale,
    ) -> str:
        """Текст лобби-карточки (заголовок + статус + длина босса + рейдеры).

        Считает оставшееся время лобби (`ceil((lobby_ends_at - now) / 60`),
        минимум 1 мин если ещё не закрыто; иначе — `bosses-lobby-status-closing`).
        """
        summoner_nick = self._render_full_nick(
            title=summoner.title,
            display_name=summoner_display_name,
            name=summoner.name,
            locale=locale,
        )
        boss_nick = self._render_full_nick(
            title=boss.title,
            display_name=boss_display_name,
            name=boss.name,
            locale=locale,
        )
        status_text = self._lobby_status_text(
            boss_fight=boss_fight,
            now=now,
            locale=locale,
        )
        return self._bundle.format(
            MessageKey("bosses-lobby-state"),
            locale=locale,
            summoner_nick=summoner_nick,
            boss_nick=boss_nick,
            lobby_status=status_text,
            boss_length_cm=boss_fight.current_boss_length_cm,
            raiders_count=raiders_count,
        )

    def lobby_keyboard(
        self,
        *,
        boss_fight_id: int,
        locale: Locale,
    ) -> InlineKeyboardMarkup:
        """Inline-клавиатура лобби: три кнопки — `join`, `leave`, `cancel`.

        Кнопки видны всем; валидацию роли (только саммонер может
        отменить, не-саммонер не может вступить дважды) делают use-case-ы.
        Раскладка: 1×3 (одна строка на три кнопки) — компактно.
        """
        join = InlineKeyboardButton(
            text=self._bundle.format(MessageKey("bosses-button-join"), locale=locale),
            callback_data=boss_callback_data(
                action="join",
                boss_fight_id=boss_fight_id,
            ),
        )
        leave = InlineKeyboardButton(
            text=self._bundle.format(MessageKey("bosses-button-leave"), locale=locale),
            callback_data=boss_callback_data(
                action="leave",
                boss_fight_id=boss_fight_id,
            ),
        )
        cancel = InlineKeyboardButton(
            text=self._bundle.format(MessageKey("bosses-button-cancel"), locale=locale),
            callback_data=boss_callback_data(
                action="cancel",
                boss_fight_id=boss_fight_id,
            ),
        )
        return InlineKeyboardMarkup(inline_keyboard=[[join, leave, cancel]])

    def _lobby_status_text(
        self,
        *,
        boss_fight: BossFight,
        now: datetime,
        locale: Locale,
    ) -> str:
        """Подстрока статуса лобби: «закроется через N мин» / «закрывается»."""
        remaining = boss_fight.lobby_ends_at - now
        remaining_seconds = remaining.total_seconds()
        if remaining_seconds <= 0:
            return self._bundle.format(
                MessageKey("bosses-lobby-status-closing"),
                locale=locale,
            )
        remaining_minutes = max(1, math.ceil(remaining_seconds / 60))
        return self._bundle.format(
            MessageKey("bosses-lobby-status-open"),
            locale=locale,
            remaining_minutes=remaining_minutes,
        )

    # --- Уведомления старта / тика раунда / финиша боя (D.7) ---

    def battle_started_text(
        self,
        *,
        summoner: Player,
        summoner_display_name: DisplayName,
        boss: Player,
        boss_display_name: DisplayName,
        boss_length_cm: int,
        raiders_count: int,
        cfg: BossesConfig,
        locale: Locale,
    ) -> str:
        """Текст «лобби закрыто, бой начался» — публикуется в чат, где
        был вызван `/boss`, сразу после `LOBBY → IN_BATTLE`.

        Использует `cfg.round_max_seconds` для информативной фразы
        «босс бьёт раз в N сек».
        """
        summoner_nick = self._render_full_nick(
            title=summoner.title,
            display_name=summoner_display_name,
            name=summoner.name,
            locale=locale,
        )
        boss_nick = self._render_full_nick(
            title=boss.title,
            display_name=boss_display_name,
            name=boss.name,
            locale=locale,
        )
        return self._bundle.format(
            MessageKey("bosses-battle-started"),
            locale=locale,
            summoner_nick=summoner_nick,
            boss_nick=boss_nick,
            raiders_count=raiders_count,
            boss_length_cm=boss_length_cm,
            round_seconds=cfg.round_max_seconds,
        )

    def round_tick_text(
        self,
        *,
        boss: Player,
        boss_display_name: DisplayName,
        round_number: int,
        boss_damage_cm: int,
        boss_length_cm: int,
        eliminated_count: int,
        raiders_alive: int,
        locale: Locale,
    ) -> str:
        """Текст карточки раунда — публикуется после каждого
        `RunBossRound`-callback-а. Содержит per-round-метрики:
        нанесённый по боссу урон, текущий HP босса, выбывшие
        рейдеры, оставшиеся.
        """
        boss_nick = self._render_full_nick(
            title=boss.title,
            display_name=boss_display_name,
            name=boss.name,
            locale=locale,
        )
        return self._bundle.format(
            MessageKey("bosses-round-tick"),
            locale=locale,
            boss_nick=boss_nick,
            round_number=round_number,
            boss_damage_cm=boss_damage_cm,
            boss_length_cm=boss_length_cm,
            eliminated_count=eliminated_count,
            raiders_alive=raiders_alive,
        )

    def battle_finished_victory_text(
        self,
        *,
        summoner: Player,
        summoner_display_name: DisplayName,
        boss: Player,
        boss_display_name: DisplayName,
        raiders_alive: int,
        per_raider_grant_cm: int,
        locale: Locale,
    ) -> str:
        """Текст «рейдеры победили» — публикуется после
        `FinishBossFight.execute()` в исходе victory (`raiders_won=True`).

        ГДД §10.5–§10.6: рейдеры делят `initial_boss_length_cm` поровну
        (round-down) + получают шанс на скролл из дроп-таблицы.
        """
        summoner_nick = self._render_full_nick(
            title=summoner.title,
            display_name=summoner_display_name,
            name=summoner.name,
            locale=locale,
        )
        boss_nick = self._render_full_nick(
            title=boss.title,
            display_name=boss_display_name,
            name=boss.name,
            locale=locale,
        )
        return self._bundle.format(
            MessageKey("bosses-battle-finished-victory"),
            locale=locale,
            summoner_nick=summoner_nick,
            boss_nick=boss_nick,
            raiders_alive=raiders_alive,
            per_raider_grant_cm=per_raider_grant_cm,
        )

    def battle_finished_defeat_text(
        self,
        *,
        summoner: Player,
        summoner_display_name: DisplayName,
        boss: Player,
        boss_display_name: DisplayName,
        raiders_alive: int,
        total_granted_cm: int,
        locale: Locale,
    ) -> str:
        """Текст «рейд провален, босс победил» — публикуется после
        `FinishBossFight.execute()` в исходе defeat (`raiders_won=False`).

        ГДД §10.5: босс забирает суммарную «недотянутую» длину рейдеров
        (= `sum(length_at_join_cm)` — clamp до min-length).
        """
        summoner_nick = self._render_full_nick(
            title=summoner.title,
            display_name=summoner_display_name,
            name=summoner.name,
            locale=locale,
        )
        boss_nick = self._render_full_nick(
            title=boss.title,
            display_name=boss_display_name,
            name=boss.name,
            locale=locale,
        )
        return self._bundle.format(
            MessageKey("bosses-battle-finished-defeat"),
            locale=locale,
            summoner_nick=summoner_nick,
            boss_nick=boss_nick,
            raiders_alive=raiders_alive,
            total_granted_cm=total_granted_cm,
        )

    @staticmethod
    def count_alive_raiders(participants: tuple[BossParticipant, ...]) -> int:
        """Подсчёт «живых» рейдеров после раунда / финиша.

        В рейд-боях все записи в `boss_participants` — это живые рейдеры
        (выбывшие удаляются из таблицы в `RunBossRound`-use-case-е,
        Спринт 3.3-C). Поэтому `len(participants)` и есть
        количество живых.
        """
        return len(participants)

    # --- Callback `boss:join:<id>` ---

    def join_toast_success(self, *, locale: Locale) -> str:
        """Toast: успешное вступление в лобби рейд-босса."""
        return self._bundle.format(MessageKey("bosses-join-toast-success"), locale=locale)

    def callback_toast_lobby_closed(self, *, locale: Locale) -> str:
        """Toast: лобби рейд-боса уже закрыто (бой/финал/отменён)."""
        return self._bundle.format(
            MessageKey("bosses-callback-toast-lobby-closed"),
            locale=locale,
        )

    def callback_toast_already_in_fight(self, *, locale: Locale) -> str:
        """Toast: игрок уже участвует в этом рейде (повторное нажатие join)."""
        return self._bundle.format(
            MessageKey("bosses-callback-toast-already-in-fight"),
            locale=locale,
        )

    def callback_toast_cannot_join_as_boss(self, *, locale: Locale) -> str:
        """Toast: игрок попытался вступить рейдером, но он сам — босс."""
        return self._bundle.format(
            MessageKey("bosses-callback-toast-cannot-join-as-boss"),
            locale=locale,
        )

    def callback_toast_requirement_thickness(
        self,
        *,
        required: int,
        actual: int,
        locale: Locale,
    ) -> str:
        """Toast: толщина < `min_thickness_level_raider` (ГДД §10.1 = 4)."""
        return self._bundle.format(
            MessageKey("bosses-callback-toast-requirement-thickness"),
            locale=locale,
            required=required,
            actual=actual,
        )

    def callback_toast_requirement_length(
        self,
        *,
        required_cm: int,
        actual_cm: int,
        locale: Locale,
    ) -> str:
        """Toast: длина < `min_length_cm` (ГДД §10.1 = 20 см)."""
        return self._bundle.format(
            MessageKey("bosses-callback-toast-requirement-length"),
            locale=locale,
            required_cm=required_cm,
            actual_cm=actual_cm,
        )

    # --- Callback `boss:leave:<id>` ---

    def leave_toast_success(self, *, locale: Locale) -> str:
        """Toast: успешный выход из лобби рейд-босса.

        Длины в лобби не списывались (списание — в `FinishBossFight`,
        ГДД §10.5), поэтому возврат не нужен.
        """
        return self._bundle.format(MessageKey("bosses-leave-toast-success"), locale=locale)

    def leave_toast_summoner_leaves(self, *, locale: Locale) -> str:
        """Toast: саммонер не может «выйти» — для этого есть «Отменить рейд».

        Use-case `LeaveBossLobby` технически разрешает саммонеру выйти,
        но в UI мы предпочитаем явный flow через «Отменить рейд» — иначе
        бой превратится в «лобби без саммонера», что плохо для UX.
        """
        return self._bundle.format(
            MessageKey("bosses-leave-toast-summoner-leaves"),
            locale=locale,
        )

    def leave_toast_not_a_participant(self, *, locale: Locale) -> str:
        """Toast: игрок не участник этого рейда (нечего покидать)."""
        return self._bundle.format(
            MessageKey("bosses-leave-toast-not-a-participant"),
            locale=locale,
        )

    # --- Callback `boss:cancel:<id>` ---

    def cancel_message_text(self, *, locale: Locale) -> str:
        """Текст, которым заменяется сообщение с кнопкой после отмены."""
        return self._bundle.format(MessageKey("bosses-cancel-message"), locale=locale)

    def cancel_toast_success(self, *, locale: Locale) -> str:
        """Toast в callback после успешной отмены рейд-боя."""
        return self._bundle.format(MessageKey("bosses-cancel-toast-success"), locale=locale)

    def cancel_toast_already_cancelled(self, *, locale: Locale) -> str:
        """Toast: рейд-бой уже отменён ранее (идемпотентный no-op)."""
        return self._bundle.format(
            MessageKey("bosses-cancel-toast-already-cancelled"),
            locale=locale,
        )

    # --- Общие callback-toast-ы рейд-боса ---

    def callback_toast_fight_not_found(self, *, locale: Locale) -> str:
        """Toast: рейд-бой не найден (мог быть удалён/не существует)."""
        return self._bundle.format(
            MessageKey("bosses-callback-toast-fight-not-found"),
            locale=locale,
        )

    def callback_toast_invalid_state(self, *, locale: Locale) -> str:
        """Toast: рейд-бой больше не в LOBBY (бой / финал / отменён)."""
        return self._bundle.format(
            MessageKey("bosses-callback-toast-invalid-state"),
            locale=locale,
        )

    def callback_toast_not_summoner(self, *, locale: Locale) -> str:
        """Toast: только саммонер может отменить рейд."""
        return self._bundle.format(
            MessageKey("bosses-callback-toast-not-summoner"),
            locale=locale,
        )

    def callback_toast_player_not_found(self, *, locale: Locale) -> str:
        """Toast: игрок не зарегистрирован — нажми /start."""
        return self._bundle.format(
            MessageKey("bosses-callback-toast-player-not-found"),
            locale=locale,
        )

    def callback_toast_player_frozen(self, *, locale: Locale) -> str:
        """Toast: игрок `FROZEN`/`BANNED` (DAU-gate / админ-заморозка)."""
        return self._bundle.format(
            MessageKey("bosses-callback-toast-player-frozen"),
            locale=locale,
        )

    def callback_toast_generic_error(self, *, locale: Locale) -> str:
        """Toast: общая ошибка (мусорный callback_data, неизвестная action)."""
        return self._bundle.format(
            MessageKey("bosses-callback-toast-generic-error"),
            locale=locale,
        )

    # --- helpers ---

    def _render_full_nick(
        self,
        *,
        title: Title | None,
        display_name: DisplayName,
        name: PlayerName | None,
        locale: Locale,
    ) -> str:
        """Собрать «полный ник»: `[Локализованный титул] [Название] [Имя]`.

        Дублирует `CaravanPresenter._render_full_nick` /
        `_PvePresenter._render_full_nick`; вынесение в общий helper
        отложено до тех пор, пока презентеров с этой логикой не станет
        ≥ 4 (правило 3 повторов уже превышено, но рефакторинг отложен
        как отдельный tech-debt-ticket).
        """
        parts: list[str] = []
        if title is not None:
            parts.append(self._bundle.format(title_message_key(title), locale=locale))
        parts.append(display_name.value)
        if name is not None:
            parts.append(name.value)
        return " ".join(parts)


__all__ = [
    "BossCallbackAction",
    "BossCallbackData",
    "BossPresenter",
    "boss_callback_data",
    "is_boss_callback",
    "parse_boss_callback_data",
]
