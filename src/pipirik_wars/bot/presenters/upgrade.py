"""Презентеры для команды `/upgrade` (Спринт 1.4.A → 1.5.D, ГДД §3.2).

Тонкий слой между use-case `UpgradeThickness` и Telegram-handler-ом.
С 1.5.D переехал на `IMessageBundle`: ключи `upgrade-*` лежат в
`locales/{ru,en}.ftl`.

Что внутри:

- **`UpgradePresenter`** — локализованные тексты карточки-предложения,
  успеха, отказа («не хватает длины»), отмены, race-сообщения,
  toast-ов, подписей кнопок.
- **`build_upgrade_proposal_keyboard(...)`** — `InlineKeyboardMarkup`
  с парой «Подтвердить (X см) / Отменить» (тексты тоже локализуются).
- **`upgrade_callback_data(...)` / `parse_upgrade_callback_data(...)`** —
  кодирование/декодирование `callback_data`. Формат:
  ``"upgrade:<action>:<expected_cost_cm>"`` ≤ 64 байта. `action` — один
  из `confirm / cancel`.

`expected_cost_cm` зашит в callback_data: handler передаёт его обратно
в use-case как `UpgradeThicknessInput.expected_cost_cm`. Это защищает
от случая «balance.yaml перегружен между показом и нажатием
Подтвердить» — use-case бросит `ConcurrencyError`, а handler покажет
понятное сообщение.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey

# Telegram callback_data hard-cap = 64 байта. Префикс + action +
# `expected_cost_cm` (до ~10 цифр) умещаются с большим запасом.
_CALLBACK_PREFIX: Final[str] = "upgrade"

UpgradeCallbackAction = Literal["confirm", "cancel"]
_VALID_ACTIONS: Final[frozenset[UpgradeCallbackAction]] = frozenset({"confirm", "cancel"})

_KEY_GROUP: Final[MessageKey] = MessageKey("upgrade-group")
_KEY_OTHER: Final[MessageKey] = MessageKey("upgrade-other")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("upgrade-not-registered")
_KEY_PROPOSAL: Final[MessageKey] = MessageKey("upgrade-proposal")
_KEY_SUCCESS: Final[MessageKey] = MessageKey("upgrade-success")
_KEY_INSUFFICIENT: Final[MessageKey] = MessageKey("upgrade-insufficient")
_KEY_INSUFFICIENT_SHORT: Final[MessageKey] = MessageKey("upgrade-insufficient-short")
_KEY_CANCELLED: Final[MessageKey] = MessageKey("upgrade-cancelled")
_KEY_RACE: Final[MessageKey] = MessageKey("upgrade-race")
_KEY_BUTTON_CONFIRM: Final[MessageKey] = MessageKey("upgrade-button-confirm")
_KEY_BUTTON_CANCEL: Final[MessageKey] = MessageKey("upgrade-button-cancel")
_KEY_TOAST_UPGRADED: Final[MessageKey] = MessageKey("upgrade-toast-upgraded")
_KEY_TOAST_CANCELLED: Final[MessageKey] = MessageKey("upgrade-toast-cancelled")
_KEY_TOAST_PLAYER_NOT_FOUND: Final[MessageKey] = MessageKey("upgrade-toast-player-not-found")
_KEY_TOAST_INSUFFICIENT: Final[MessageKey] = MessageKey("upgrade-toast-insufficient")
_KEY_TOAST_RACE: Final[MessageKey] = MessageKey("upgrade-toast-race")
_KEY_ANTICHEAT_BLOCKED: Final[MessageKey] = MessageKey("upgrade-anticheat-blocked")
_KEY_TOAST_ANTICHEAT: Final[MessageKey] = MessageKey("upgrade-toast-anticheat-blocked")


@dataclass(frozen=True, slots=True)
class UpgradeCallbackData:
    """Распаршенный `callback_data` инлайн-кнопки `/upgrade`.

    `expected_cost_cm` — стоимость, которую UI показал пользователю.
    Use-case `UpgradeThickness` сверяется с актуальной стоимостью и
    бросает `ConcurrencyError` при расхождении. `0` для `cancel`-кнопки.
    """

    action: UpgradeCallbackAction
    expected_cost_cm: int


class UpgradePresenter:
    """Локализованный фасад над `IMessageBundle` для команды `/upgrade`.

    Включая клавиатуру: метод `proposal_keyboard(cost_cm, locale)`
    собирает `InlineKeyboardMarkup` с локализованными подписями
    «Подтвердить (X см)» / «Отменить» (а вот `callback_data` остаётся
    invariant — он не зависит от локали).
    """

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- chat-ветки ---------------------------------------------------

    def group(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GROUP, locale=locale)

    def other(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_OTHER, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    # --- карточки -----------------------------------------------------

    def proposal(
        self,
        *,
        current_thickness: int,
        cost_cm: int,
        current_length_cm: int,
        min_after_spend_cm: int,
        locale: Locale,
    ) -> str:
        """Карточка подтверждения «Прокачать с N до N+1?»."""
        return self._bundle.format(
            _KEY_PROPOSAL,
            locale=locale,
            current_thickness=current_thickness,
            next_thickness=current_thickness + 1,
            cost_cm=cost_cm,
            current_length_cm=current_length_cm,
            remaining_cm=current_length_cm - cost_cm,
            min_after_spend_cm=min_after_spend_cm,
        )

    def success(
        self,
        *,
        new_thickness: int,
        cost_cm: int,
        new_length_cm: int,
        locale: Locale,
    ) -> str:
        """Подтверждение «Толщина прокачана» после успеха use-case-а."""
        return self._bundle.format(
            _KEY_SUCCESS,
            locale=locale,
            new_thickness=new_thickness,
            cost_cm=cost_cm,
            new_length_cm=new_length_cm,
        )

    def insufficient(
        self,
        *,
        current_thickness: int,
        cost_cm: int,
        current_length_cm: int,
        deficit_cm: int,
        min_after_spend_cm: int,
        locale: Locale,
    ) -> str:
        """Текст ответа при `InsufficientLengthError` (правило 20 см)."""
        return self._bundle.format(
            _KEY_INSUFFICIENT,
            locale=locale,
            next_thickness=current_thickness + 1,
            cost_cm=cost_cm,
            current_length_cm=current_length_cm,
            min_after_spend_cm=min_after_spend_cm,
            deficit_cm=deficit_cm,
        )

    def insufficient_short(
        self,
        *,
        cost_cm: int,
        current_length_cm: int,
        min_after_spend_cm: int,
        deficit_cm: int,
        locale: Locale,
    ) -> str:
        """Сжатый текст «Недостаточно длины» — для `edit_text` после
        нажатия `Подтвердить`. Без полной карточки — handler не знает
        свежий `thickness` без повторного `GetProfile`.
        """
        return self._bundle.format(
            _KEY_INSUFFICIENT_SHORT,
            locale=locale,
            cost_cm=cost_cm,
            current_length_cm=current_length_cm,
            min_after_spend_cm=min_after_spend_cm,
            deficit_cm=deficit_cm,
        )

    def cancelled(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_CANCELLED, locale=locale)

    def race(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_RACE, locale=locale)

    def anticheat_blocked(self, *, banned_until: str, locale: Locale) -> str:
        """Текст ответа при `AnticheatSoftBanError` (Спринт 1.6.E).

        :param banned_until: ISO-8601 строка момента истечения бана
            (UTC, tz-aware, обычно `exc.banned_until.isoformat()`).
        """
        return self._bundle.format(
            _KEY_ANTICHEAT_BLOCKED,
            locale=locale,
            **{"banned-until": banned_until},
        )

    # --- toast-ы (≤ 200 символов) -------------------------------------

    def toast_upgraded(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_UPGRADED, locale=locale)

    def toast_cancelled(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_CANCELLED, locale=locale)

    def toast_player_not_found(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_PLAYER_NOT_FOUND, locale=locale)

    def toast_insufficient(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_INSUFFICIENT, locale=locale)

    def toast_race(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_RACE, locale=locale)

    def toast_anticheat_blocked(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_ANTICHEAT, locale=locale)

    # --- клавиатура ---------------------------------------------------

    def proposal_keyboard(
        self,
        *,
        expected_cost_cm: int,
        locale: Locale,
    ) -> InlineKeyboardMarkup:
        """Инлайн-клавиатура «Подтвердить / Отменить» под карточкой /upgrade.

        Подписи кнопок локализованы; `callback_data` остаётся
        локаль-независимым (зависит только от action + cost).
        """
        confirm_label = self._bundle.format(
            _KEY_BUTTON_CONFIRM,
            locale=locale,
            cost_cm=expected_cost_cm,
        )
        cancel_label = self._bundle.format(_KEY_BUTTON_CANCEL, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=confirm_label,
                        callback_data=upgrade_callback_data("confirm", expected_cost_cm),
                    ),
                    InlineKeyboardButton(
                        text=cancel_label,
                        callback_data=upgrade_callback_data("cancel", 0),
                    ),
                ],
            ]
        )


def upgrade_callback_data(action: UpgradeCallbackAction, expected_cost_cm: int) -> str:
    """Сериализовать `callback_data` для инлайн-кнопки /upgrade.

    Формат: ``"upgrade:<action>:<expected_cost_cm>"``. `expected_cost_cm`
    ≥ 0 (для `cancel` всегда 0). Бросает `ValueError` при невалидных
    аргументах.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown upgrade action: {action!r}")
    if expected_cost_cm < 0:
        raise ValueError(f"expected_cost_cm must be >= 0, got {expected_cost_cm}")
    return f"{_CALLBACK_PREFIX}:{action}:{expected_cost_cm}"


def parse_upgrade_callback_data(raw: str) -> UpgradeCallbackData:
    """Распарсить `callback_data` инлайн-кнопки /upgrade.

    Бросает `ValueError`, если формат не совпадает (старый клиент,
    форвард чужого сообщения, повреждённые данные).
    """
    parts = raw.split(":")
    if len(parts) != 3:
        raise ValueError(f"invalid upgrade callback_data: {raw!r}")
    prefix, action, expected_cost_raw = parts
    if prefix != _CALLBACK_PREFIX:
        raise ValueError(f"invalid upgrade callback_data prefix: {prefix!r}")
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown upgrade action: {action!r}")
    try:
        expected_cost_cm = int(expected_cost_raw)
    except ValueError as exc:
        raise ValueError(f"invalid expected_cost_cm in {raw!r}") from exc
    if expected_cost_cm < 0:
        raise ValueError(f"expected_cost_cm must be >= 0, got {expected_cost_cm}")
    return UpgradeCallbackData(
        action=_as_action(action),
        expected_cost_cm=expected_cost_cm,
    )


def _as_action(raw: str) -> UpgradeCallbackAction:
    """Сузить строку до union-типа `UpgradeCallbackAction` без `type: ignore`."""
    if raw == "confirm":
        return "confirm"
    if raw == "cancel":
        return "cancel"
    raise ValueError(f"unknown upgrade action: {raw!r}")


__all__ = [
    "UpgradeCallbackAction",
    "UpgradeCallbackData",
    "UpgradePresenter",
    "parse_upgrade_callback_data",
    "upgrade_callback_data",
]
