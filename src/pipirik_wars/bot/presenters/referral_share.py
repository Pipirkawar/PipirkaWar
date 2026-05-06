"""Презентер «Поделиться» с реферальной ссылкой (Спринт 2.4.D-b, ГДД §13.2).

Генерирует:
- Текст share-сообщения (дуэль или поход) с `t.me/pipirik_bot?start=ref_<tg_id>`
- Inline-клавиатуру с одной кнопкой, несущей `ref-share:{kind}:{entity_id}`

Используется:
- В `duel.py` — как замена/дополнение к `pvp-share` (2.1.H).
- В `notifications/forest.py` — добавляется в finish-keyboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey

# ────────────────────────── constants ──────────────────────────

_PREFIX: Final[str] = "ref-share"
_BOT_USERNAME: Final[str] = "pipirik_bot"

_KEY_BUTTON: Final[MessageKey] = MessageKey("referral-share-button")
_KEY_DUEL_VICTORY: Final[MessageKey] = MessageKey("referral-share-duel-victory")
_KEY_DUEL_DRAW: Final[MessageKey] = MessageKey("referral-share-duel-draw")
_KEY_FOREST: Final[MessageKey] = MessageKey("referral-share-forest")


# ────────────────────────── enums / DTOs ──────────────────────────


class ShareKind(StrEnum):
    DUEL = "duel"
    FOREST = "forest"


@dataclass(frozen=True, slots=True)
class ReferralShareCallbackData:
    kind: ShareKind
    entity_id: int


# ────────────────────────── callback_data helpers ──────────────────────────


def referral_share_callback_data(kind: ShareKind, entity_id: int) -> str:
    """Сериализовать `ref-share:{kind}:{entity_id}`."""
    if entity_id <= 0:
        raise ValueError(f"entity_id must be positive: {entity_id}")
    return f"{_PREFIX}:{kind.value}:{entity_id}"


def parse_referral_share_callback_data(data: str) -> ReferralShareCallbackData:
    """Распарсить `ref-share:{kind}:{entity_id}`. Бросает ValueError."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != _PREFIX:
        raise ValueError(f"invalid ref-share callback_data: {data!r}")
    try:
        kind = ShareKind(parts[1])
    except ValueError as exc:
        raise ValueError(f"unknown share kind: {parts[1]!r}") from exc
    try:
        entity_id = int(parts[2])
    except ValueError as exc:
        raise ValueError(f"entity_id must be int: {parts[2]!r}") from exc
    if entity_id <= 0:
        raise ValueError(f"entity_id must be positive: {entity_id}")
    return ReferralShareCallbackData(kind=kind, entity_id=entity_id)


# ────────────────────────── deeplink helper ──────────────────────────


def _build_deeplink(sharer_tg_id: int) -> str:
    return f"t.me/{_BOT_USERNAME}?start=ref_{sharer_tg_id}"


# ────────────────────────── presenter ──────────────────────────


class ReferralSharePresenter:
    """Форматирует share-тексты (§13.2) и клавиатуры."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- текст ---

    def share_text_duel_victory(
        self,
        *,
        winner_name: str,
        loser_name: str,
        delta_cm: int,
        winner_length_cm: int,
        sharer_tg_id: int,
        locale: Locale,
    ) -> str:
        return self._bundle.format(
            _KEY_DUEL_VICTORY,
            locale=locale,
            winner=winner_name,
            loser=loser_name,
            delta_cm=delta_cm,
            winner_length_cm=winner_length_cm,
            deeplink=_build_deeplink(sharer_tg_id),
        )

    def share_text_duel_draw(
        self,
        *,
        p1_name: str,
        p2_name: str,
        sharer_tg_id: int,
        locale: Locale,
    ) -> str:
        return self._bundle.format(
            _KEY_DUEL_DRAW,
            locale=locale,
            p1=p1_name,
            p2=p2_name,
            deeplink=_build_deeplink(sharer_tg_id),
        )

    def share_text_forest(
        self,
        *,
        player_name: str,
        delta_cm: int,
        length_cm: int,
        sharer_tg_id: int,
        locale: Locale,
    ) -> str:
        return self._bundle.format(
            _KEY_FOREST,
            locale=locale,
            player=player_name,
            delta_cm=delta_cm,
            length_cm=length_cm,
            deeplink=_build_deeplink(sharer_tg_id),
        )

    # --- клавиатуры ---

    def share_button_duel(self, *, duel_id: int, locale: Locale) -> InlineKeyboardButton:
        """Одна кнопка «Поделиться» для `/duel` (для встраивания в чужие kbrd)."""
        label = self._bundle.format(_KEY_BUTTON, locale=locale)
        return InlineKeyboardButton(
            text=label,
            callback_data=referral_share_callback_data(ShareKind.DUEL, duel_id),
        )

    def share_button_forest(self, *, run_id: int, locale: Locale) -> InlineKeyboardButton:
        """Одна кнопка «Поделиться» для `/forest` (для встраивания в чужие kbrd)."""
        label = self._bundle.format(_KEY_BUTTON, locale=locale)
        return InlineKeyboardButton(
            text=label,
            callback_data=referral_share_callback_data(ShareKind.FOREST, run_id),
        )

    def share_keyboard_duel(self, *, duel_id: int, locale: Locale) -> InlineKeyboardMarkup:
        label = self._bundle.format(_KEY_BUTTON, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=referral_share_callback_data(ShareKind.DUEL, duel_id),
                    ),
                ],
            ],
        )

    def share_keyboard_forest(self, *, run_id: int, locale: Locale) -> InlineKeyboardMarkup:
        label = self._bundle.format(_KEY_BUTTON, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=referral_share_callback_data(ShareKind.FOREST, run_id),
                    ),
                ],
            ],
        )


__all__ = [
    "ReferralShareCallbackData",
    "ReferralSharePresenter",
    "ShareKind",
    "parse_referral_share_callback_data",
    "referral_share_callback_data",
]
