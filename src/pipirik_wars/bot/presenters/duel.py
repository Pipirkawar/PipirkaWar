"""Презентер команды `/duel` (Спринт 2.1.E, ГДД §7.1).

Тонкий слой между PvP use-case-ами (`ChallengeDuel` / `AcceptDuel` /
`CancelDuel` / `SubmitMove`) и Telegram-handler-ом.
Ключи `duel-*` лежат в `locales/{ru,en}.ftl`.

Что внутри:

- **`DuelPresenter`** — локализованные тексты вызова, приёма, отмены,
  раунд-промптов, результата боя, тостов и сообщений об ошибках
  (player-not-found, anti-cheat soft-ban, requirements, lock-conflict,
  not-a-participant, invalid-state).
- **Кейборды** под сообщения:
  * `challenge_keyboard(...)` — `[Принять] [Отклонить]` под адресным
    вызовом в чате; для `chat_only` / `chat_then_global`.
  * `attack_keyboard(...)` — 3 кнопки `[High] [Mid] [Low]` для выбора
    атаки в раунде.
  * `block_keyboard(...)` — 3 кнопки для выбора блока (атака уже
    выбрана и зашита в `callback_data`).
- **`callback_data`-сериализация**: `pvp-accept:<duel_id>`,
  `pvp-reject:<duel_id>`, `pvp-attack:<duel_id>:<round_num>:<position>`,
  `pvp-block:<duel_id>:<round_num>:<attack>:<position>`. Все callback-data
  ≤ 64 байт (`pvp-block` — самый длинный, ~30 байт).

`callback_data` не зависит от локали; подписи кнопок — зависят.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.domain.pvp import Position

# --- Callback-data --------------------------------------------------------

# Префиксы; общий header `pvp-` для всех PvP-кнопок.
_PREFIX_ACCEPT: Final[str] = "pvp-accept"
_PREFIX_REJECT: Final[str] = "pvp-reject"
_PREFIX_ATTACK: Final[str] = "pvp-attack"
_PREFIX_BLOCK: Final[str] = "pvp-block"

# Допустимые значения для `Position`-кодов в callback_data.
_POSITION_VALUES: Final[frozenset[str]] = frozenset({"high", "mid", "low"})


@dataclass(frozen=True, slots=True)
class AcceptCallbackData:
    """Распаршенный `callback_data` кнопки «Принять»."""

    duel_id: int


@dataclass(frozen=True, slots=True)
class RejectCallbackData:
    """Распаршенный `callback_data` кнопки «Отклонить»."""

    duel_id: int


@dataclass(frozen=True, slots=True)
class AttackCallbackData:
    """Распаршенный `callback_data` кнопки выбора атаки.

    `position` — `"high"` / `"mid"` / `"low"`. `round_num` — номер
    раунда, в котором делается ход (1..3).
    """

    duel_id: int
    round_num: int
    position: Literal["high", "mid", "low"]


@dataclass(frozen=True, slots=True)
class BlockCallbackData:
    """Распаршенный `callback_data` кнопки выбора блока.

    `attack` уже выбран на предыдущем шаге и зашит в callback_data,
    чтобы handler мог собрать `RoundChoice(attack, block)`.
    """

    duel_id: int
    round_num: int
    attack: Literal["high", "mid", "low"]
    position: Literal["high", "mid", "low"]


def accept_callback_data(duel_id: int) -> str:
    """Сериализовать `pvp-accept:<duel_id>`."""
    if duel_id <= 0:
        raise ValueError(f"duel_id must be positive: {duel_id}")
    return f"{_PREFIX_ACCEPT}:{duel_id}"


def reject_callback_data(duel_id: int) -> str:
    """Сериализовать `pvp-reject:<duel_id>`."""
    if duel_id <= 0:
        raise ValueError(f"duel_id must be positive: {duel_id}")
    return f"{_PREFIX_REJECT}:{duel_id}"


def attack_callback_data(duel_id: int, round_num: int, position: Position) -> str:
    """Сериализовать `pvp-attack:<duel_id>:<round_num>:<position>`."""
    if duel_id <= 0 or round_num <= 0:
        raise ValueError(f"duel_id and round_num must be positive: {duel_id}, {round_num}")
    return f"{_PREFIX_ATTACK}:{duel_id}:{round_num}:{position.value}"


def block_callback_data(
    duel_id: int,
    round_num: int,
    attack: Position,
    position: Position,
) -> str:
    """Сериализовать `pvp-block:<duel_id>:<round_num>:<attack>:<position>`."""
    if duel_id <= 0 or round_num <= 0:
        raise ValueError(f"duel_id and round_num must be positive: {duel_id}, {round_num}")
    return f"{_PREFIX_BLOCK}:{duel_id}:{round_num}:{attack.value}:{position.value}"


def parse_accept_callback_data(data: str) -> AcceptCallbackData:
    """Распарсить `pvp-accept:<duel_id>`. Бросает `ValueError` при невалидной строке."""
    parts = data.split(":")
    if len(parts) != 2 or parts[0] != _PREFIX_ACCEPT:
        raise ValueError(f"invalid pvp-accept callback_data: {data!r}")
    duel_id = _parse_positive_int(parts[1], field="duel_id")
    return AcceptCallbackData(duel_id=duel_id)


def parse_reject_callback_data(data: str) -> RejectCallbackData:
    """Распарсить `pvp-reject:<duel_id>`."""
    parts = data.split(":")
    if len(parts) != 2 or parts[0] != _PREFIX_REJECT:
        raise ValueError(f"invalid pvp-reject callback_data: {data!r}")
    duel_id = _parse_positive_int(parts[1], field="duel_id")
    return RejectCallbackData(duel_id=duel_id)


def parse_attack_callback_data(data: str) -> AttackCallbackData:
    """Распарсить `pvp-attack:<duel_id>:<round_num>:<position>`."""
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != _PREFIX_ATTACK:
        raise ValueError(f"invalid pvp-attack callback_data: {data!r}")
    duel_id = _parse_positive_int(parts[1], field="duel_id")
    round_num = _parse_positive_int(parts[2], field="round_num")
    position = _parse_position(parts[3])
    return AttackCallbackData(duel_id=duel_id, round_num=round_num, position=position)


def parse_block_callback_data(data: str) -> BlockCallbackData:
    """Распарсить `pvp-block:<duel_id>:<round_num>:<attack>:<position>`."""
    parts = data.split(":")
    if len(parts) != 5 or parts[0] != _PREFIX_BLOCK:
        raise ValueError(f"invalid pvp-block callback_data: {data!r}")
    duel_id = _parse_positive_int(parts[1], field="duel_id")
    round_num = _parse_positive_int(parts[2], field="round_num")
    attack = _parse_position(parts[3])
    position = _parse_position(parts[4])
    return BlockCallbackData(
        duel_id=duel_id,
        round_num=round_num,
        attack=attack,
        position=position,
    )


def _parse_positive_int(raw: str, *, field: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be int, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{field} must be positive, got {value}")
    return value


def _parse_position(raw: str) -> Literal["high", "mid", "low"]:
    if raw not in _POSITION_VALUES:
        raise ValueError(f"position must be one of {_POSITION_VALUES}, got {raw!r}")
    # Узкое сужение для mypy — после проверки `raw in _POSITION_VALUES`
    # значение точно один из трёх литералов.
    if raw == "high":
        return "high"
    if raw == "mid":
        return "mid"
    return "low"


# --- MessageKey-константы -------------------------------------------------

# Чат-валидация (`/duel`-команда).
_KEY_PRIVATE_NEEDS_GLOBAL: Final[MessageKey] = MessageKey("duel-private-needs-global")
_KEY_USAGE: Final[MessageKey] = MessageKey("duel-usage")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("duel-not-registered")
_KEY_TARGET_NOT_REGISTERED: Final[MessageKey] = MessageKey("duel-target-not-registered")
_KEY_TARGET_IS_BOT: Final[MessageKey] = MessageKey("duel-target-is-bot")
_KEY_SELF_CHALLENGE: Final[MessageKey] = MessageKey("duel-self-challenge")

# Карточка вызова в чате (chat_only / chat_then_global).
_KEY_CHALLENGE_CHAT: Final[MessageKey] = MessageKey("duel-challenge-chat")
_KEY_CHALLENGE_CHAT_THEN_GLOBAL: Final[MessageKey] = MessageKey("duel-challenge-chat-then-global")
# Подтверждение global_only (без чата).
_KEY_CHALLENGE_GLOBAL: Final[MessageKey] = MessageKey("duel-challenge-global")
_KEY_GLOBAL_ENQUEUED: Final[MessageKey] = MessageKey("duel-global-enqueued")
_KEY_GLOBAL_MATCHED: Final[MessageKey] = MessageKey("duel-global-matched")
_KEY_GLOBAL_EMPTY: Final[MessageKey] = MessageKey("duel-global-empty")
_KEY_GLOBAL_ONLY_IN_PRIVATE: Final[MessageKey] = MessageKey("duel-global-only-in-private")

# Кнопки.
_KEY_BTN_ACCEPT: Final[MessageKey] = MessageKey("duel-button-accept")
_KEY_BTN_REJECT: Final[MessageKey] = MessageKey("duel-button-reject")
_KEY_BTN_ATTACK_HIGH: Final[MessageKey] = MessageKey("duel-button-attack-high")
_KEY_BTN_ATTACK_MID: Final[MessageKey] = MessageKey("duel-button-attack-mid")
_KEY_BTN_ATTACK_LOW: Final[MessageKey] = MessageKey("duel-button-attack-low")
_KEY_BTN_BLOCK_HIGH: Final[MessageKey] = MessageKey("duel-button-block-high")
_KEY_BTN_BLOCK_MID: Final[MessageKey] = MessageKey("duel-button-block-mid")
_KEY_BTN_BLOCK_LOW: Final[MessageKey] = MessageKey("duel-button-block-low")

# Раунд-промпты (DM игрокам).
_KEY_ROUND_ATTACK_PROMPT: Final[MessageKey] = MessageKey("duel-round-attack-prompt")
_KEY_ROUND_BLOCK_PROMPT: Final[MessageKey] = MessageKey("duel-round-block-prompt")
_KEY_ROUND_WAITING: Final[MessageKey] = MessageKey("duel-round-waiting")

# Результат боя (DM).
_KEY_RESULT_VICTORY: Final[MessageKey] = MessageKey("duel-result-victory")
_KEY_RESULT_DEFEAT: Final[MessageKey] = MessageKey("duel-result-defeat")
_KEY_RESULT_DRAW: Final[MessageKey] = MessageKey("duel-result-draw")

# Карточка отмены и тостов.
_KEY_CANCELLED: Final[MessageKey] = MessageKey("duel-cancelled")
_KEY_CANCEL_USAGE: Final[MessageKey] = MessageKey("duel-cancel-usage")
_KEY_CHAT_ACCEPTED: Final[MessageKey] = MessageKey("duel-chat-accepted")

# Toasts (≤ 200 символов).
_KEY_TOAST_ACCEPTED: Final[MessageKey] = MessageKey("duel-toast-accepted")
_KEY_TOAST_REJECTED: Final[MessageKey] = MessageKey("duel-toast-rejected")
_KEY_TOAST_CANCELLED: Final[MessageKey] = MessageKey("duel-toast-cancelled")
_KEY_TOAST_DUEL_NOT_FOUND: Final[MessageKey] = MessageKey("duel-toast-not-found")
_KEY_TOAST_NOT_PARTICIPANT: Final[MessageKey] = MessageKey("duel-toast-not-participant")
_KEY_TOAST_FOREIGN_BUTTON: Final[MessageKey] = MessageKey("duel-toast-foreign-button")
_KEY_TOAST_INVALID_STATE: Final[MessageKey] = MessageKey("duel-toast-invalid-state")
_KEY_TOAST_ALREADY_SUBMITTED: Final[MessageKey] = MessageKey("duel-toast-already-submitted")
_KEY_TOAST_OUTDATED: Final[MessageKey] = MessageKey("duel-toast-outdated")

# Полные ошибки (отправляются как сообщения, а не toast).
_KEY_REQUIREMENTS: Final[MessageKey] = MessageKey("duel-requirements-not-met")
_KEY_ANTICHEAT_BLOCKED: Final[MessageKey] = MessageKey("duel-anticheat-blocked")
_KEY_LOCK_HELD: Final[MessageKey] = MessageKey("duel-lock-already-held")


class DuelPresenter:
    """Локализованный фасад над `IMessageBundle` для `/duel`-handler-ов."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- /duel-команда: chat-валидация и usage ------------------------

    def private_needs_global(self, *, locale: Locale) -> str:
        """Текст в ЛС: подсказка использовать `/duel` без аргументов для глобал-режима."""
        return self._bundle.format(_KEY_PRIVATE_NEEDS_GLOBAL, locale=locale)

    def usage(self, *, locale: Locale) -> str:
        """Подсказка по использованию в групповом чате (без reply)."""
        return self._bundle.format(_KEY_USAGE, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    def target_not_registered(self, *, locale: Locale) -> str:
        """Reply-цель не зарегистрирована в боте."""
        return self._bundle.format(_KEY_TARGET_NOT_REGISTERED, locale=locale)

    def target_is_bot(self, *, locale: Locale) -> str:
        """Попытка вызвать бота на дуэль."""
        return self._bundle.format(_KEY_TARGET_IS_BOT, locale=locale)

    def self_challenge(self, *, locale: Locale) -> str:
        """Reply на собственное сообщение."""
        return self._bundle.format(_KEY_SELF_CHALLENGE, locale=locale)

    # --- Карточки вызова в чате ---------------------------------------

    def challenge_chat_only(
        self,
        *,
        challenger_username: str,
        challenged_username: str,
        locale: Locale,
    ) -> str:
        """Карточка `chat_only`-вызова в группе (адресный)."""
        return self._bundle.format(
            _KEY_CHALLENGE_CHAT,
            locale=locale,
            challenger=challenger_username,
            challenged=challenged_username,
        )

    def challenge_chat_then_global(
        self,
        *,
        challenger_username: str,
        challenged_username: str,
        locale: Locale,
    ) -> str:
        """Карточка `chat_then_global`-вызова в группе."""
        return self._bundle.format(
            _KEY_CHALLENGE_CHAT_THEN_GLOBAL,
            locale=locale,
            challenger=challenger_username,
            challenged=challenged_username,
        )

    def challenge_global(
        self,
        *,
        challenger_username: str,
        ttl_minutes: int,
        locale: Locale,
    ) -> str:
        """Карточка `global_only`-вызова (отправляется в ЛС челленджеру)."""
        return self._bundle.format(
            _KEY_CHALLENGE_GLOBAL,
            locale=locale,
            challenger=challenger_username,
            ttl_minutes=ttl_minutes,
        )

    # --- /duel_global и глобал-лобби (Спринт 2.1.F.3) -------------

    def global_enqueued(
        self,
        *,
        duel_id: int,
        ttl_minutes: int,
        locale: Locale,
    ) -> str:
        """Ответ в ЛС на `/duel` без аргументов — вызов поставлен в глобал-лобби."""
        return self._bundle.format(
            _KEY_GLOBAL_ENQUEUED,
            locale=locale,
            duel_id=duel_id,
            ttl_minutes=ttl_minutes,
        )

    def global_matched(
        self,
        *,
        challenger_username: str,
        locale: Locale,
    ) -> str:
        """Ответ в ЛС на `/duel_global` — успешный матч с ждущим в лобби."""
        return self._bundle.format(
            _KEY_GLOBAL_MATCHED,
            locale=locale,
            challenger=challenger_username,
        )

    def global_empty(self, *, locale: Locale) -> str:
        """Ответ в ЛС на `/duel_global` — лобби пусто (или race со своим вызовом)."""
        return self._bundle.format(_KEY_GLOBAL_EMPTY, locale=locale)

    def global_only_in_private(self, *, locale: Locale) -> str:
        """`/duel_global` в групповом чате или супергруппе — нельзя."""
        return self._bundle.format(_KEY_GLOBAL_ONLY_IN_PRIVATE, locale=locale)

    def chat_accepted(
        self,
        *,
        challenger_username: str,
        challenged_username: str,
        locale: Locale,
    ) -> str:
        """Текст для замены challenge-сообщения после приёма."""
        return self._bundle.format(
            _KEY_CHAT_ACCEPTED,
            locale=locale,
            challenger=challenger_username,
            challenged=challenged_username,
        )

    def cancelled(
        self,
        *,
        challenger_username: str,
        locale: Locale,
    ) -> str:
        """Текст для замены challenge-сообщения после отмены."""
        return self._bundle.format(
            _KEY_CANCELLED,
            locale=locale,
            challenger=challenger_username,
        )

    def cancel_usage(self, *, locale: Locale) -> str:
        """Подсказка `/cancel_duel <id>` без аргументов."""
        return self._bundle.format(_KEY_CANCEL_USAGE, locale=locale)

    # --- Раунд-промпты (DM игроку) ------------------------------------

    def round_attack_prompt(self, *, round_num: int, locale: Locale) -> str:
        """«Раунд N: выбери атаку»."""
        return self._bundle.format(
            _KEY_ROUND_ATTACK_PROMPT,
            locale=locale,
            round_num=round_num,
        )

    def round_block_prompt(
        self,
        *,
        round_num: int,
        attack: Position,
        locale: Locale,
    ) -> str:
        """«Раунд N: атака — X. Выбери блок»."""
        return self._bundle.format(
            _KEY_ROUND_BLOCK_PROMPT,
            locale=locale,
            round_num=round_num,
            attack=attack.value,
        )

    def round_waiting(self, *, round_num: int, locale: Locale) -> str:
        """«Раунд N: твой ход принят, ждём оппонента»."""
        return self._bundle.format(
            _KEY_ROUND_WAITING,
            locale=locale,
            round_num=round_num,
        )

    # --- Результат боя (DM) -------------------------------------------

    def result_victory(
        self,
        *,
        delta_cm: int,
        new_length_cm: int,
        locale: Locale,
    ) -> str:
        """Победа: `+delta_cm` к длине."""
        return self._bundle.format(
            _KEY_RESULT_VICTORY,
            locale=locale,
            delta_cm=delta_cm,
            new_length_cm=new_length_cm,
        )

    def result_defeat(
        self,
        *,
        delta_cm: int,
        new_length_cm: int,
        locale: Locale,
    ) -> str:
        """Поражение: `delta_cm` к длине (delta_cm < 0)."""
        return self._bundle.format(
            _KEY_RESULT_DEFEAT,
            locale=locale,
            delta_cm=delta_cm,
            new_length_cm=new_length_cm,
        )

    def result_draw(
        self,
        *,
        length_cm: int,
        locale: Locale,
    ) -> str:
        """Ничья: длина не изменилась."""
        return self._bundle.format(
            _KEY_RESULT_DRAW,
            locale=locale,
            length_cm=length_cm,
        )

    # --- Полные ошибки (сообщения) ------------------------------------

    def requirements_not_met(
        self,
        *,
        min_length_cm: int,
        min_thickness_level: int,
        locale: Locale,
    ) -> str:
        """`PvpRequirementsNotMetError` — длина/толщина ниже порога."""
        return self._bundle.format(
            _KEY_REQUIREMENTS,
            locale=locale,
            min_length_cm=min_length_cm,
            min_thickness_level=min_thickness_level,
        )

    def anticheat_blocked(self, *, banned_until: str, locale: Locale) -> str:
        """`AnticheatSoftBanError` — soft-ban активен."""
        return self._bundle.format(
            _KEY_ANTICHEAT_BLOCKED,
            locale=locale,
            **{"banned-until": banned_until},
        )

    def lock_already_held(self, *, locale: Locale) -> str:
        """`LockAlreadyHeldError` — игрок занят (например, в `/forest`)."""
        return self._bundle.format(_KEY_LOCK_HELD, locale=locale)

    # --- Toasts (≤ 200 символов) --------------------------------------

    def toast_accepted(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_ACCEPTED, locale=locale)

    def toast_rejected(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_REJECTED, locale=locale)

    def toast_cancelled(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_CANCELLED, locale=locale)

    def toast_duel_not_found(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_DUEL_NOT_FOUND, locale=locale)

    def toast_not_participant(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_NOT_PARTICIPANT, locale=locale)

    def toast_foreign_button(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_FOREIGN_BUTTON, locale=locale)

    def toast_invalid_state(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_INVALID_STATE, locale=locale)

    def toast_already_submitted(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_ALREADY_SUBMITTED, locale=locale)

    def toast_outdated(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_OUTDATED, locale=locale)

    # --- Клавиатуры ---------------------------------------------------

    def challenge_keyboard(
        self,
        *,
        duel_id: int,
        locale: Locale,
    ) -> InlineKeyboardMarkup:
        """`[Принять] [Отклонить]` под адресным вызовом в чате."""
        accept_label = self._bundle.format(_KEY_BTN_ACCEPT, locale=locale)
        reject_label = self._bundle.format(_KEY_BTN_REJECT, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=accept_label,
                        callback_data=accept_callback_data(duel_id),
                    ),
                    InlineKeyboardButton(
                        text=reject_label,
                        callback_data=reject_callback_data(duel_id),
                    ),
                ],
            ],
        )

    def attack_keyboard(
        self,
        *,
        duel_id: int,
        round_num: int,
        locale: Locale,
    ) -> InlineKeyboardMarkup:
        """3 кнопки выбора атаки: `[High] [Mid] [Low]`."""
        high_label = self._bundle.format(_KEY_BTN_ATTACK_HIGH, locale=locale)
        mid_label = self._bundle.format(_KEY_BTN_ATTACK_MID, locale=locale)
        low_label = self._bundle.format(_KEY_BTN_ATTACK_LOW, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=high_label,
                        callback_data=attack_callback_data(duel_id, round_num, Position.HIGH),
                    ),
                    InlineKeyboardButton(
                        text=mid_label,
                        callback_data=attack_callback_data(duel_id, round_num, Position.MID),
                    ),
                    InlineKeyboardButton(
                        text=low_label,
                        callback_data=attack_callback_data(duel_id, round_num, Position.LOW),
                    ),
                ],
            ],
        )

    def block_keyboard(
        self,
        *,
        duel_id: int,
        round_num: int,
        attack: Position,
        locale: Locale,
    ) -> InlineKeyboardMarkup:
        """3 кнопки выбора блока (атака уже выбрана)."""
        high_label = self._bundle.format(_KEY_BTN_BLOCK_HIGH, locale=locale)
        mid_label = self._bundle.format(_KEY_BTN_BLOCK_MID, locale=locale)
        low_label = self._bundle.format(_KEY_BTN_BLOCK_LOW, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=high_label,
                        callback_data=block_callback_data(
                            duel_id, round_num, attack, Position.HIGH
                        ),
                    ),
                    InlineKeyboardButton(
                        text=mid_label,
                        callback_data=block_callback_data(duel_id, round_num, attack, Position.MID),
                    ),
                    InlineKeyboardButton(
                        text=low_label,
                        callback_data=block_callback_data(duel_id, round_num, attack, Position.LOW),
                    ),
                ],
            ],
        )


__all__ = [
    "AcceptCallbackData",
    "AttackCallbackData",
    "BlockCallbackData",
    "DuelPresenter",
    "RejectCallbackData",
    "accept_callback_data",
    "attack_callback_data",
    "block_callback_data",
    "parse_accept_callback_data",
    "parse_attack_callback_data",
    "parse_block_callback_data",
    "parse_reject_callback_data",
    "reject_callback_data",
]
