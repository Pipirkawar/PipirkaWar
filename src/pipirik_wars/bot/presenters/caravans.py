"""Презентер `/caravan`-ветки (Спринт 3.2-D, ГДД §9).

Отвечает за все локализованные сообщения handler-а `/caravan`:
ответ-инструкции (групповой чат, не-личка, незарегистрированный игрок),
ошибки (gate по толщине / длине, кулдаун клана, конфликт ролей,
заморозка), сообщения об успехе (подтверждение лидеру в личке +
объявление в чате клана-отправителя). Вся i18n идёт через
`IMessageBundle` — handler никогда не клеит строки сам.

Lobby-UI (inline-кнопки «вступить как X» × 3 ролей + «отменить»),
сообщения о финале боя и сценарии «вернулись из похода» — будут
добавлены в D.3 / D.4 этого же модуля.

Сериализация `callback_data` для inline-кнопок — отдельный
free-form helper (`caravan_callback_data` / `parse_caravan_callback_data`)
в этом же модуле; держим её рядом с презентером по тому же
паттерну, что у forest / mountains / dungeon (одна точка истины
для префикса `caravan:` и форматов событий).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.bot.presenters.profile import title_message_key
from pipirik_wars.domain.balance import CaravansConfig
from pipirik_wars.domain.caravan import Caravan, CaravanParticipant, CaravanRole
from pipirik_wars.domain.player import DisplayName, Player, PlayerName, Title

_CARAVAN_CALLBACK_PREFIX: Final[str] = "caravan"

CaravanCallbackAction = Literal[
    "show_lobby",
    "join_defender",
    "join_raider",
    "leave",
    "cancel",
]
_VALID_ACTIONS: Final[frozenset[CaravanCallbackAction]] = frozenset(
    {
        "show_lobby",
        "join_defender",
        "join_raider",
        "leave",
        "cancel",
    },
)


@dataclass(frozen=True, slots=True)
class CaravanCallbackData:
    """Распаршенный `callback_data` инлайн-кнопки каравана.

    `caravan:<action>:<caravan_id>`. Поддерживаемые `action`-ы:

    - `show_lobby` — открыть лобби в личке (под объявлением в чате
      клана-отправителя; добавлено в D.2);
    - `join_defender` / `join_raider` — вступить в лобби как защитник
      / рейдер (без `contribution`, добавлено в D.3);
    - `leave` — выйти из лобби (для не-лидеров, D.3);
    - `cancel` — отменить караван (только лидер, D.3).

    Для `join_caravaneer` инлайн-кнопки нет: вступление караванщиком
    требует размер взноса, поэтому делается отдельной командой
    `/caravan_join <caravan_id> <contribution_cm>` в личке.
    """

    action: CaravanCallbackAction
    caravan_id: int


def caravan_callback_data(*, action: CaravanCallbackAction, caravan_id: int) -> str:
    """Сериализовать `callback_data` инлайн-кнопки каравана.

    Формат: `caravan:<action>:<caravan_id>`. Telegram callback_data
    — 64 байт жёстко; для `caravan_id` до 19 знаков и `action` до 16
    символов укладываемся с большим запасом.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown caravan callback action: {action!r}")
    if caravan_id <= 0:
        raise ValueError(f"caravan_id must be > 0, got {caravan_id}")
    return f"{_CARAVAN_CALLBACK_PREFIX}:{action}:{caravan_id}"


def parse_caravan_callback_data(data: str) -> CaravanCallbackData:
    """Распарсить `callback_data` каравана. На любой мусор — `ValueError`."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != _CARAVAN_CALLBACK_PREFIX:
        raise ValueError(f"caravan callback_data must be 'caravan:<action>:<id>', got {data!r}")
    _, action_raw, caravan_id_raw = parts
    action: CaravanCallbackAction
    if action_raw == "show_lobby":
        action = "show_lobby"
    elif action_raw == "join_defender":
        action = "join_defender"
    elif action_raw == "join_raider":
        action = "join_raider"
    elif action_raw == "leave":
        action = "leave"
    elif action_raw == "cancel":
        action = "cancel"
    else:
        raise ValueError(f"unknown caravan action: {action_raw!r}")
    try:
        caravan_id = int(caravan_id_raw)
    except ValueError as exc:
        raise ValueError(f"caravan_id must be int, got {caravan_id_raw!r}") from exc
    if caravan_id <= 0:
        raise ValueError(f"caravan_id must be > 0, got {caravan_id}")
    return CaravanCallbackData(action=action, caravan_id=caravan_id)


def is_caravan_callback(data: str | None) -> bool:
    """Filter helper — это callback каравана?

    Используется handler-ом через `F.data.startswith(...)`-фильтр,
    чтобы не пересекаться с forest / mountains / dungeon.
    """
    if data is None:
        return False
    return data.startswith(f"{_CARAVAN_CALLBACK_PREFIX}:")


class CaravanPresenter:
    """Локализованный рендер ответов `/caravan`-handler-а через `IMessageBundle`.

    Использует префикс ключей `caravans-*` (множественное число —
    исторический выбор файла локалей: караваны как игровая механика,
    в отличие от единичного `forest`/`mountains`/`dungeon`).
    """

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- Команда `/caravan` — где её пускать ---

    def group(self, *, locale: Locale) -> str:
        """Команда вызвана в групповом чате — инструкция «открой ЛС»."""
        return self._bundle.format(MessageKey("caravans-group"), locale=locale)

    def other(self, *, locale: Locale) -> str:
        """Команда вызвана не в групповом и не в приватном (channel и т.п.)."""
        return self._bundle.format(MessageKey("caravans-other"), locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        """`PlayerNotFoundError` — игрок не нажимал /start."""
        return self._bundle.format(MessageKey("caravans-not-registered"), locale=locale)

    # --- Команда `/caravan` — usage / парсинг аргументов ---

    def usage(self, *, locale: Locale) -> str:
        """Игрок вызвал `/caravan` без двух аргументов или с не-парой."""
        return self._bundle.format(MessageKey("caravans-usage"), locale=locale)

    def receiver_invalid(self, *, value: str, locale: Locale) -> str:
        """Первый аргумент не парсится в `int` (chat_id)."""
        return self._bundle.format(
            MessageKey("caravans-receiver-invalid"),
            locale=locale,
            value=value,
        )

    def contribution_invalid(self, *, value: str, locale: Locale) -> str:
        """Второй аргумент не парсится в положительное `int` (взнос в см)."""
        return self._bundle.format(
            MessageKey("caravans-contribution-invalid"),
            locale=locale,
            value=value,
        )

    # --- Команда `/caravan` — отказы по правилам и состоянию ---

    def no_clan(self, *, locale: Locale) -> str:
        """Игрок не состоит ни в одном клане."""
        return self._bundle.format(MessageKey("caravans-no-clan"), locale=locale)

    def not_a_leader(self, *, locale: Locale) -> str:
        """Игрок состоит в клане, но он не лидер."""
        return self._bundle.format(MessageKey("caravans-not-a-leader"), locale=locale)

    def receiver_not_found(self, *, chat_id: int, locale: Locale) -> str:
        """`receiver_chat_id` не зарегистрирован как клан."""
        return self._bundle.format(
            MessageKey("caravans-receiver-not-found"),
            locale=locale,
            chat_id=chat_id,
        )

    def receiver_same_as_sender(self, *, locale: Locale) -> str:
        """Лидер передал chat_id своего же клана — `_validate_clans_differ`."""
        return self._bundle.format(MessageKey("caravans-receiver-same-as-sender"), locale=locale)

    def already_in(self, *, locale: Locale) -> str:
        """У клана уже идёт активный караван (`AlreadyInCaravanError`)."""
        return self._bundle.format(MessageKey("caravans-already-in"), locale=locale)

    def cooldown(self, *, remaining_seconds: int, locale: Locale) -> str:
        """Кулдаун между караванами клана (`CaravanCooldownError`)."""
        # Округляем вверх до минут — ниже минуты UX-смысла нет, плюс это
        # совпадает с тем, как игрок видит лобби (минуты, не секунды).
        remaining_minutes = max(1, (remaining_seconds + 59) // 60)
        return self._bundle.format(
            MessageKey("caravans-cooldown"),
            locale=locale,
            remaining_minutes=remaining_minutes,
        )

    def requirement_thickness(self, *, required: int, actual: int, locale: Locale) -> str:
        """Толщина < `min_thickness_level_leader` (ГДД §9.1 = 7)."""
        return self._bundle.format(
            MessageKey("caravans-requirement-thickness"),
            locale=locale,
            required=required,
            actual=actual,
        )

    def requirement_length(self, *, required_cm: int, actual_cm: int, locale: Locale) -> str:
        """`length - contribution_cm < min_length_after_contribution_cm` (ГДД §9.2 = 20)."""
        return self._bundle.format(
            MessageKey("caravans-requirement-length"),
            locale=locale,
            required_cm=required_cm,
            actual_cm=actual_cm,
        )

    def player_frozen(self, *, locale: Locale) -> str:
        """Игрок `FROZEN`/`BANNED` (DAU-gate)."""
        return self._bundle.format(MessageKey("caravans-player-frozen"), locale=locale)

    def clan_frozen_sender(self, *, locale: Locale) -> str:
        """Клан-отправитель заморожен (`ClanFrozenError` на sender)."""
        return self._bundle.format(MessageKey("caravans-clan-frozen-sender"), locale=locale)

    def clan_frozen_receiver(self, *, locale: Locale) -> str:
        """Клан-получатель заморожен (`ClanFrozenError` на receiver)."""
        return self._bundle.format(MessageKey("caravans-clan-frozen-receiver"), locale=locale)

    # --- Команда `/caravan` — успех ---

    def created_private(
        self,
        *,
        receiver_clan_name: str,
        contribution_cm: int,
        lobby_minutes: int,
        locale: Locale,
    ) -> str:
        """Подтверждение лидеру в личке: караван создан, объявление ушло."""
        return self._bundle.format(
            MessageKey("caravans-created-private"),
            locale=locale,
            receiver_clan_name=receiver_clan_name,
            contribution_cm=contribution_cm,
            lobby_minutes=lobby_minutes,
        )

    def created_announcement(
        self,
        *,
        leader: Player,
        leader_display_name: DisplayName,
        receiver_clan_name: str,
        contribution_cm: int,
        lobby_minutes: int,
        locale: Locale,
    ) -> str:
        """Объявление в чате клана-отправителя: лидер собирает караван."""
        leader_nick = self._render_full_nick(
            title=leader.title,
            display_name=leader_display_name,
            name=leader.name,
            locale=locale,
        )
        return self._bundle.format(
            MessageKey("caravans-created-announcement"),
            locale=locale,
            leader_nick=leader_nick,
            receiver_clan_name=receiver_clan_name,
            contribution_cm=contribution_cm,
            lobby_minutes=lobby_minutes,
        )

    def announcement_keyboard(
        self,
        *,
        caravan_id: int,
        locale: Locale,
    ) -> InlineKeyboardMarkup:
        """Inline-клавиатура под объявлением: единственная кнопка
        «Показать лобби» (full lobby UI — в D.3).
        """
        button = InlineKeyboardButton(
            text=self._bundle.format(MessageKey("caravans-button-show-lobby"), locale=locale),
            callback_data=caravan_callback_data(
                action="show_lobby",
                caravan_id=caravan_id,
            ),
        )
        return InlineKeyboardMarkup(inline_keyboard=[[button]])

    # --- Callback `caravan:show_lobby:<id>` (D.3c) ---

    def lobby_state_text(
        self,
        *,
        caravan: Caravan,
        participants: tuple[CaravanParticipant, ...],
        leader: Player,
        leader_display_name: DisplayName,
        receiver_clan_name: str,
        cfg: CaravansConfig,
        now: datetime,
        locale: Locale,
    ) -> str:
        """Текст лобби-сообщения (заголовок + статус + ростер по ролям).

        Считает оставшееся время лобби (`ceil((lobby_ends_at - now) / 60`),
        минимум 1 мин если ещё не закрыто; иначе — `caravans-lobby-status-closing`).
        Ростер — счётчики по ролям + capacity-капы (defenders/raiders), плюс
        суммарный взнос всех `CARAVANEER`-ов (включая лидера).
        """
        leader_nick = self._render_full_nick(
            title=leader.title,
            display_name=leader_display_name,
            name=leader.name,
            locale=locale,
        )
        caravaneers = [p for p in participants if p.role is CaravanRole.CARAVANEER]
        defenders = [p for p in participants if p.role is CaravanRole.DEFENDER]
        raiders = [p for p in participants if p.role is CaravanRole.RAIDER]
        total_contribution_cm = sum(
            (p.contribution.cm for p in caravaneers if p.contribution is not None),
            start=0,
        )
        defenders_cap = cfg.max_defenders_per_caravaneer * len(caravaneers)
        raiders_cap = cfg.max_raiders_per_caravaneer * len(caravaneers)
        status_text = self._lobby_status_text(
            caravan=caravan,
            now=now,
            locale=locale,
        )
        return self._bundle.format(
            MessageKey("caravans-lobby-state"),
            locale=locale,
            leader_nick=leader_nick,
            receiver_clan_name=receiver_clan_name,
            lobby_status=status_text,
            caravaneers_count=len(caravaneers),
            total_contribution_cm=total_contribution_cm,
            defenders_count=len(defenders),
            defenders_cap=defenders_cap,
            raiders_count=len(raiders),
            raiders_cap=raiders_cap,
        )

    def lobby_keyboard(
        self,
        *,
        caravan_id: int,
        locale: Locale,
    ) -> InlineKeyboardMarkup:
        """Inline-клавиатура лобби: четыре кнопки — `join_defender`,
        `join_raider`, `leave`, `cancel`.

        Кнопки видны всем (валидацию роли/лидерства делают use-case-ы);
        для CARAVANEER-роли отдельной кнопки нет — там нужен `contribution`,
        поэтому используется команда `/caravan_join` (D.3f).

        Раскладка: 2×2 (две кнопки в строке, две строки).
        """
        join_defender = InlineKeyboardButton(
            text=self._bundle.format(
                MessageKey("caravans-button-join-defender"),
                locale=locale,
            ),
            callback_data=caravan_callback_data(
                action="join_defender",
                caravan_id=caravan_id,
            ),
        )
        join_raider = InlineKeyboardButton(
            text=self._bundle.format(
                MessageKey("caravans-button-join-raider"),
                locale=locale,
            ),
            callback_data=caravan_callback_data(
                action="join_raider",
                caravan_id=caravan_id,
            ),
        )
        leave = InlineKeyboardButton(
            text=self._bundle.format(MessageKey("caravans-button-leave"), locale=locale),
            callback_data=caravan_callback_data(
                action="leave",
                caravan_id=caravan_id,
            ),
        )
        cancel = InlineKeyboardButton(
            text=self._bundle.format(MessageKey("caravans-button-cancel"), locale=locale),
            callback_data=caravan_callback_data(
                action="cancel",
                caravan_id=caravan_id,
            ),
        )
        return InlineKeyboardMarkup(
            inline_keyboard=[[join_defender, join_raider], [leave, cancel]],
        )

    def _lobby_status_text(
        self,
        *,
        caravan: Caravan,
        now: datetime,
        locale: Locale,
    ) -> str:
        """Подстрока статуса лобби: «закроется через N мин» / «закрывается»."""
        remaining = caravan.lobby_ends_at - now
        remaining_seconds = remaining.total_seconds()
        if remaining_seconds <= 0:
            return self._bundle.format(
                MessageKey("caravans-lobby-status-closing"),
                locale=locale,
            )
        remaining_minutes = max(1, math.ceil(remaining_seconds / 60))
        return self._bundle.format(
            MessageKey("caravans-lobby-status-open"),
            locale=locale,
            remaining_minutes=remaining_minutes,
        )

    # --- Callback `caravan:join_defender|join_raider:<id>` (D.3d) ---

    def join_toast_success(
        self,
        *,
        role: Literal["defender", "raider"],
        locale: Locale,
    ) -> str:
        """Toast: успешное вступление в лобби каравана как defender/raider.

        Отдельный ключ на каждую роль — текст в локалях разный («ты
        теперь защитник» / «ты теперь рейдер»).
        """
        if role == "defender":
            key = MessageKey("caravans-join-toast-success-defender")
        else:
            key = MessageKey("caravans-join-toast-success-raider")
        return self._bundle.format(key, locale=locale)

    def callback_toast_lobby_closed(self, *, locale: Locale) -> str:
        """Toast: лобби каравана уже закрылось (бой/финал/отменён)."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-lobby-closed"),
            locale=locale,
        )

    def callback_toast_player_frozen(self, *, locale: Locale) -> str:
        """Toast: игрок `FROZEN`/`BANNED` (DAU-gate / админ-заморозка)."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-player-frozen"),
            locale=locale,
        )

    def callback_toast_already_in_caravan(self, *, locale: Locale) -> str:
        """Toast: игрок уже участвует в этом или другом активном караване."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-already-in-caravan"),
            locale=locale,
        )

    def callback_toast_role_conflict_defender(self, *, locale: Locale) -> str:
        """Toast: чтобы быть защитником, надо состоять в клане-получателе."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-role-conflict-defender"),
            locale=locale,
        )

    def callback_toast_role_conflict_raider(self, *, locale: Locale) -> str:
        """Toast: рейдер не должен состоять ни в клане-отправителе, ни в получателе."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-role-conflict-raider"),
            locale=locale,
        )

    def callback_toast_capacity_defender(self, *, limit: int, locale: Locale) -> str:
        """Toast: достигнут лимит защитников (`max_defenders × CARAVANEER count`)."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-capacity-defender"),
            locale=locale,
            limit=limit,
        )

    def callback_toast_capacity_raider(self, *, limit: int, locale: Locale) -> str:
        """Toast: достигнут лимит рейдеров (`max_raiders × CARAVANEER count`)."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-capacity-raider"),
            locale=locale,
            limit=limit,
        )

    def callback_toast_requirement_thickness(
        self,
        *,
        required: int,
        actual: int,
        locale: Locale,
    ) -> str:
        """Toast: толщина < `min_thickness_level_raider` (ГДД §9.5 = 5)."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-requirement-thickness"),
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
        """Toast: длина < общего минимума (`min_length_cm`, ГДД §9.2 = 20 см)."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-requirement-length"),
            locale=locale,
            required_cm=required_cm,
            actual_cm=actual_cm,
        )

    # --- Callback `caravan:leave:<id>` (D.3e) ---

    def leave_toast_success(self, *, returned_contribution_cm: int, locale: Locale) -> str:
        """Toast: успешный выход из лобби каравана.

        Если у игрока был ненулевой `contribution` (т.е. он входил
        как `CARAVANEER`, см. `LeftCaravanLobby.returned_contribution_cm`)
        — отдаём отдельный ключ с суммой возврата; иначе короткий toast.
        Длина игрока на лобби-стадии и так не списана (списание — в
        момент `LOBBY → IN_BATTLE`, ГДД §9.3), поэтому «возврат» здесь
        — это потенциальный взнос, который игрок «забрал обратно».
        """
        if returned_contribution_cm > 0:
            return self._bundle.format(
                MessageKey("caravans-leave-toast-success-with-contribution"),
                locale=locale,
                contribution_cm=returned_contribution_cm,
            )
        return self._bundle.format(
            MessageKey("caravans-leave-toast-success"),
            locale=locale,
        )

    def leave_toast_leader_cannot_leave(self, *, locale: Locale) -> str:
        """Toast: лидер не может «выйти» — для этого есть «Отменить караван»."""
        return self._bundle.format(
            MessageKey("caravans-leave-toast-leader-cannot-leave"),
            locale=locale,
        )

    def leave_toast_not_a_participant(self, *, locale: Locale) -> str:
        """Toast: игрок не участник этого каравана (нечего покидать)."""
        return self._bundle.format(
            MessageKey("caravans-leave-toast-not-a-participant"),
            locale=locale,
        )

    # --- Команда `/caravan_join` (D.3f) ---

    def join_usage(self, *, locale: Locale) -> str:
        """Игрок вызвал `/caravan_join` без двух аргументов или с не-парой."""
        return self._bundle.format(MessageKey("caravans-join-usage"), locale=locale)

    def join_caravan_id_invalid(self, *, value: str, locale: Locale) -> str:
        """Первый аргумент `/caravan_join` не парсится в положительный `int`."""
        return self._bundle.format(
            MessageKey("caravans-join-caravan-id-invalid"),
            locale=locale,
            value=value,
        )

    def join_success_caravaneer(self, *, contribution_cm: int, locale: Locale) -> str:
        """Подтверждение в личке: ты вступил как CARAVANEER со взносом X см."""
        return self._bundle.format(
            MessageKey("caravans-join-success-caravaneer"),
            locale=locale,
            contribution_cm=contribution_cm,
        )

    def join_role_conflict_caravaneer(self, *, locale: Locale) -> str:
        """`CaravanRoleConflictError` для роли `caravaneer` — игрок не в
        клане-отправителе.
        """
        return self._bundle.format(
            MessageKey("caravans-join-role-conflict-caravaneer"),
            locale=locale,
        )

    # --- Callback `caravan:cancel:<id>` (D.3) ---

    def cancel_message_text(self, *, locale: Locale) -> str:
        """Текст, которым заменяется сообщение с кнопкой после отмены."""
        return self._bundle.format(MessageKey("caravans-cancel-message"), locale=locale)

    def cancel_toast_success(self, *, locale: Locale) -> str:
        """Toast в callback после успешной отмены каравана."""
        return self._bundle.format(MessageKey("caravans-cancel-toast-success"), locale=locale)

    def cancel_toast_already_cancelled(self, *, locale: Locale) -> str:
        """Toast: караван уже отменён ранее (идемпотентный no-op)."""
        return self._bundle.format(
            MessageKey("caravans-cancel-toast-already-cancelled"),
            locale=locale,
        )

    # --- Общие callback-toast-ы каравана (D.3) ---

    def callback_toast_caravan_not_found(self, *, locale: Locale) -> str:
        """Toast: караван не найден (мог быть удалён/не существует)."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-caravan-not-found"),
            locale=locale,
        )

    def callback_toast_invalid_state(self, *, locale: Locale) -> str:
        """Toast: караван больше не в LOBBY (бой / финал / отменён)."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-invalid-state"),
            locale=locale,
        )

    def callback_toast_not_a_leader(self, *, locale: Locale) -> str:
        """Toast: только лидер может отменить караван."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-not-a-leader"),
            locale=locale,
        )

    def callback_toast_player_not_found(self, *, locale: Locale) -> str:
        """Toast: игрок не зарегистрирован — нажми /start."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-player-not-found"),
            locale=locale,
        )

    def callback_toast_generic_error(self, *, locale: Locale) -> str:
        """Toast: общая ошибка (мусорный callback_data, неизвестная action)."""
        return self._bundle.format(
            MessageKey("caravans-callback-toast-generic-error"),
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

        Дублирует `_PvePresenter._render_full_nick`; вынесение в общий
        helper отложено до тех пор, пока презентеров с этой логикой не
        станет ≥ 3 (правило 3 повторов).
        """
        parts: list[str] = []
        if title is not None:
            parts.append(self._bundle.format(title_message_key(title), locale=locale))
        parts.append(display_name.value)
        if name is not None:
            parts.append(name.value)
        return " ".join(parts)


__all__ = [
    "CaravanCallbackAction",
    "CaravanCallbackData",
    "CaravanPresenter",
    "caravan_callback_data",
    "is_caravan_callback",
    "parse_caravan_callback_data",
]
