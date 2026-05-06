"""Презентер `/clan_attack` и масс-PvP callback-ов (Спринт 2.2.F, ГДД §7.2).

Тонкий слой между mass-duel use-case-ами (`StartMassDuel` /
`SubmitMassMove` / `ResolveMassDuel` / `ForceResolveMassDuel` /
`CancelMassDuel`) и Telegram-handler-ом.

UX-модель массового PvP отличается от 1×1:

* Команда `/clan_attack` запускается из группового чата клана (не из ЛС).
* Подтверждения «accept/reject» нет — обе стороны автозаписываются
  use-case-ом `StartMassDuel`.
* Каждый участник получает в ЛС последовательно: prompt-атаки →
  prompt-блока → «жди остальных» → итог боя.
* Раунд один (массовый бой одно-тиковый, ГДД §7.2 / 2.2.4), поэтому
  `round_num` в callback_data не нужен.

`callback_data` префикс — `pvpm-` (mass), чтобы не пересекаться с 1×1
`pvp-`-семейством. Все строки ≤ 64 байт по требованию Telegram.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.domain.pvp import MassDuelWinner, Position

# --- Callback-data --------------------------------------------------------

_PREFIX_ATTACK: Final[str] = "pvpm-attack"
_PREFIX_BLOCK: Final[str] = "pvpm-block"

_POSITION_VALUES: Final[frozenset[str]] = frozenset({"high", "mid", "low"})


@dataclass(frozen=True, slots=True)
class MassAttackCallbackData:
    """Распаршенный `callback_data` кнопки выбора атаки в масс-бою."""

    duel_id: int
    position: Literal["high", "mid", "low"]


@dataclass(frozen=True, slots=True)
class MassBlockCallbackData:
    """Распаршенный `callback_data` кнопки выбора блока в масс-бою.

    `attack` уже выбран на предыдущем шаге и зашит в callback_data,
    чтобы handler мог собрать `MassRoundChoice(player_id, attack, block)`.
    """

    duel_id: int
    attack: Literal["high", "mid", "low"]
    position: Literal["high", "mid", "low"]


def mass_attack_callback_data(duel_id: int, position: Position) -> str:
    """Сериализовать `pvpm-attack:<duel_id>:<position>`."""
    if duel_id <= 0:
        raise ValueError(f"duel_id must be positive: {duel_id}")
    return f"{_PREFIX_ATTACK}:{duel_id}:{position.value}"


def mass_block_callback_data(
    duel_id: int,
    attack: Position,
    position: Position,
) -> str:
    """Сериализовать `pvpm-block:<duel_id>:<attack>:<position>`."""
    if duel_id <= 0:
        raise ValueError(f"duel_id must be positive: {duel_id}")
    return f"{_PREFIX_BLOCK}:{duel_id}:{attack.value}:{position.value}"


def parse_mass_attack_callback_data(data: str) -> MassAttackCallbackData:
    """Распарсить `pvpm-attack:<duel_id>:<position>`."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != _PREFIX_ATTACK:
        raise ValueError(f"invalid pvpm-attack callback_data: {data!r}")
    duel_id = _parse_positive_int(parts[1], field="duel_id")
    position = _parse_position(parts[2])
    return MassAttackCallbackData(duel_id=duel_id, position=position)


def parse_mass_block_callback_data(data: str) -> MassBlockCallbackData:
    """Распарсить `pvpm-block:<duel_id>:<attack>:<position>`."""
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != _PREFIX_BLOCK:
        raise ValueError(f"invalid pvpm-block callback_data: {data!r}")
    duel_id = _parse_positive_int(parts[1], field="duel_id")
    attack = _parse_position(parts[2])
    position = _parse_position(parts[3])
    return MassBlockCallbackData(duel_id=duel_id, attack=attack, position=position)


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
    if raw == "high":
        return "high"
    if raw == "mid":
        return "mid"
    return "low"


# --- MessageKey-константы -------------------------------------------------

# /clan_attack chat-валидация и usage.
_KEY_NEEDS_GROUP_CHAT: Final[MessageKey] = MessageKey("pvp-mass-needs-group-chat")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("pvp-mass-not-registered")
_KEY_ATTACKER_NOT_FOUND: Final[MessageKey] = MessageKey("pvp-mass-attacker-not-found")
_KEY_ATTACKER_NOT_MEMBER: Final[MessageKey] = MessageKey("pvp-mass-attacker-not-member")
_KEY_TARGET_NOT_FOUND: Final[MessageKey] = MessageKey("pvp-mass-target-not-found")
_KEY_TARGET_NEEDED: Final[MessageKey] = MessageKey("pvp-mass-target-needed")
_KEY_SELF_ATTACK: Final[MessageKey] = MessageKey("pvp-mass-self-attack")
_KEY_CLAN_FROZEN: Final[MessageKey] = MessageKey("pvp-mass-clan-frozen")
_KEY_COOLDOWN: Final[MessageKey] = MessageKey("pvp-mass-cooldown")
_KEY_NO_PARTICIPANTS: Final[MessageKey] = MessageKey("pvp-mass-no-participants")
_KEY_LOCK_HELD: Final[MessageKey] = MessageKey("pvp-mass-lock-already-held")

# Карточка старта.
_KEY_STARTED: Final[MessageKey] = MessageKey("pvp-mass-started")

# DM-промпты.
_KEY_PROMPT_ATTACK: Final[MessageKey] = MessageKey("pvp-mass-prompt-attack")
_KEY_PROMPT_BLOCK: Final[MessageKey] = MessageKey("pvp-mass-prompt-block")
_KEY_WAITING: Final[MessageKey] = MessageKey("pvp-mass-waiting")

# Финал.
_KEY_RESULT_VICTORY: Final[MessageKey] = MessageKey("pvp-mass-result-victory")
_KEY_RESULT_DEFEAT: Final[MessageKey] = MessageKey("pvp-mass-result-defeat")
_KEY_RESULT_DRAW: Final[MessageKey] = MessageKey("pvp-mass-result-draw")
_KEY_RESULT_CHAT_VICTORY: Final[MessageKey] = MessageKey("pvp-mass-result-chat-victory")
_KEY_RESULT_CHAT_DRAW: Final[MessageKey] = MessageKey("pvp-mass-result-chat-draw")

# Кнопки.
_KEY_BTN_ATTACK_HIGH: Final[MessageKey] = MessageKey("pvp-mass-button-attack-high")
_KEY_BTN_ATTACK_MID: Final[MessageKey] = MessageKey("pvp-mass-button-attack-mid")
_KEY_BTN_ATTACK_LOW: Final[MessageKey] = MessageKey("pvp-mass-button-attack-low")
_KEY_BTN_BLOCK_HIGH: Final[MessageKey] = MessageKey("pvp-mass-button-block-high")
_KEY_BTN_BLOCK_MID: Final[MessageKey] = MessageKey("pvp-mass-button-block-mid")
_KEY_BTN_BLOCK_LOW: Final[MessageKey] = MessageKey("pvp-mass-button-block-low")

# Toast-уведомления.
_KEY_TOAST_NOT_FOUND: Final[MessageKey] = MessageKey("pvp-mass-toast-not-found")
_KEY_TOAST_NOT_PARTICIPANT: Final[MessageKey] = MessageKey("pvp-mass-toast-not-participant")
_KEY_TOAST_FOREIGN_BUTTON: Final[MessageKey] = MessageKey("pvp-mass-toast-foreign-button")
_KEY_TOAST_INVALID_STATE: Final[MessageKey] = MessageKey("pvp-mass-toast-invalid-state")
_KEY_TOAST_ALREADY_SUBMITTED: Final[MessageKey] = MessageKey("pvp-mass-toast-already-submitted")
_KEY_TOAST_OUTDATED: Final[MessageKey] = MessageKey("pvp-mass-toast-outdated")
_KEY_TOAST_ATTACK_SELECTED: Final[MessageKey] = MessageKey("pvp-mass-toast-attack-selected")
_KEY_TOAST_MOVE_ACCEPTED: Final[MessageKey] = MessageKey("pvp-mass-toast-move-accepted")


def _delta_sign(delta_cm: int) -> str:
    if delta_cm > 0:
        return "+"
    if delta_cm < 0:
        return "−"
    return ""


class MassDuelPresenter:
    """Локализованный фасад над `IMessageBundle` для масс-PvP handler-а."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- /clan_attack chat-валидация и ошибки ------------------------

    def needs_group_chat(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NEEDS_GROUP_CHAT, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    def attacker_not_found(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_ATTACKER_NOT_FOUND, locale=locale)

    def attacker_not_member(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_ATTACKER_NOT_MEMBER, locale=locale)

    def target_not_found(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TARGET_NOT_FOUND, locale=locale)

    def target_needed(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TARGET_NEEDED, locale=locale)

    def self_attack(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_SELF_ATTACK, locale=locale)

    def clan_frozen(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_CLAN_FROZEN, locale=locale)

    def cooldown(self, *, cooldown_hours: int, locale: Locale) -> str:
        return self._bundle.format(
            _KEY_COOLDOWN,
            locale=locale,
            cooldown_hours=cooldown_hours,
        )

    def no_participants(
        self,
        *,
        min_length_cm: int,
        min_thickness_level: int,
        locale: Locale,
    ) -> str:
        return self._bundle.format(
            _KEY_NO_PARTICIPANTS,
            locale=locale,
            min_length_cm=min_length_cm,
            min_thickness_level=min_thickness_level,
        )

    def lock_already_held(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_LOCK_HELD, locale=locale)

    # --- Карточка старта ------------------------------------------------

    def started_card(
        self,
        *,
        attacker_title: str,
        defender_title: str,
        attacker_size: int,
        defender_size: int,
        timer_seconds: int,
        locale: Locale,
    ) -> str:
        return self._bundle.format(
            _KEY_STARTED,
            locale=locale,
            attacker=attacker_title,
            defender=defender_title,
            attacker_size=attacker_size,
            defender_size=defender_size,
            timer_seconds=timer_seconds,
        )

    # --- DM-промпты -----------------------------------------------------

    def prompt_attack(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_PROMPT_ATTACK, locale=locale)

    def prompt_block(self, *, attack: Position, locale: Locale) -> str:
        return self._bundle.format(
            _KEY_PROMPT_BLOCK,
            locale=locale,
            attack=attack.value,
        )

    def waiting(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_WAITING, locale=locale)

    # --- Финальный результат -------------------------------------------

    def result_victory_dm(
        self,
        *,
        winner_clan_title: str,
        total_dealt: int,
        delta_cm: int,
        locale: Locale,
    ) -> str:
        return self._bundle.format(
            _KEY_RESULT_VICTORY,
            locale=locale,
            clan=winner_clan_title,
            total_dealt=total_dealt,
            delta_sign=_delta_sign(delta_cm),
            delta_cm=abs(delta_cm),
        )

    def result_defeat_dm(
        self,
        *,
        loser_clan_title: str,
        total_lost: int,
        delta_cm: int,
        locale: Locale,
    ) -> str:
        return self._bundle.format(
            _KEY_RESULT_DEFEAT,
            locale=locale,
            clan=loser_clan_title,
            total_lost=total_lost,
            delta_sign=_delta_sign(delta_cm),
            delta_cm=abs(delta_cm),
        )

    def result_draw_dm(self, *, delta_cm: int, locale: Locale) -> str:
        return self._bundle.format(
            _KEY_RESULT_DRAW,
            locale=locale,
            delta_sign=_delta_sign(delta_cm),
            delta_cm=abs(delta_cm),
        )

    def result_chat(
        self,
        *,
        winner: MassDuelWinner,
        winner_clan_title: str,
        total_dealt: int,
        locale: Locale,
    ) -> str:
        if winner is MassDuelWinner.DRAW:
            return self._bundle.format(
                _KEY_RESULT_CHAT_DRAW,
                locale=locale,
                total_dealt=total_dealt,
            )
        return self._bundle.format(
            _KEY_RESULT_CHAT_VICTORY,
            locale=locale,
            clan=winner_clan_title,
            total_dealt=total_dealt,
        )

    # --- Toast-ы --------------------------------------------------------

    def toast_not_found(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_NOT_FOUND, locale=locale)

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

    def toast_attack_selected(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_ATTACK_SELECTED, locale=locale)

    def toast_move_accepted(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_MOVE_ACCEPTED, locale=locale)

    # --- Клавиатуры -----------------------------------------------------

    def attack_keyboard(self, *, duel_id: int, locale: Locale) -> InlineKeyboardMarkup:
        """3 кнопки выбора атаки: `[High] [Mid] [Low]`."""
        high_label = self._bundle.format(_KEY_BTN_ATTACK_HIGH, locale=locale)
        mid_label = self._bundle.format(_KEY_BTN_ATTACK_MID, locale=locale)
        low_label = self._bundle.format(_KEY_BTN_ATTACK_LOW, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=high_label,
                        callback_data=mass_attack_callback_data(duel_id, Position.HIGH),
                    ),
                    InlineKeyboardButton(
                        text=mid_label,
                        callback_data=mass_attack_callback_data(duel_id, Position.MID),
                    ),
                    InlineKeyboardButton(
                        text=low_label,
                        callback_data=mass_attack_callback_data(duel_id, Position.LOW),
                    ),
                ],
            ],
        )

    def block_keyboard(
        self,
        *,
        duel_id: int,
        attack: Position,
        locale: Locale,
    ) -> InlineKeyboardMarkup:
        """3 кнопки выбора блока (атака уже выбрана и зашита в callback_data)."""
        high_label = self._bundle.format(_KEY_BTN_BLOCK_HIGH, locale=locale)
        mid_label = self._bundle.format(_KEY_BTN_BLOCK_MID, locale=locale)
        low_label = self._bundle.format(_KEY_BTN_BLOCK_LOW, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=high_label,
                        callback_data=mass_block_callback_data(duel_id, attack, Position.HIGH),
                    ),
                    InlineKeyboardButton(
                        text=mid_label,
                        callback_data=mass_block_callback_data(duel_id, attack, Position.MID),
                    ),
                    InlineKeyboardButton(
                        text=low_label,
                        callback_data=mass_block_callback_data(duel_id, attack, Position.LOW),
                    ),
                ],
            ],
        )


__all__ = [
    "MassAttackCallbackData",
    "MassBlockCallbackData",
    "MassDuelPresenter",
    "mass_attack_callback_data",
    "mass_block_callback_data",
    "parse_mass_attack_callback_data",
    "parse_mass_block_callback_data",
]
