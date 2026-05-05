"""Презентеры для команды `/upgrade` (Спринт 1.4.A, ГДД §3.2).

Тонкий слой рендеринга для bot-handler-а:

- **`render_upgrade_proposal(...)`** — текст карточки подтверждения
  «Прокачать с N до N+1: стоимость XXXX см» (показывается после
  `/upgrade`, до `Подтвердить`).
- **`render_upgrade_success(...)`** — текст после успешной прокачки.
- **`render_upgrade_insufficient(...)`** — текст «нужно ещё N см» при
  отказе из-за правила 20 см.
- **`build_upgrade_proposal_keyboard(...)`** — `InlineKeyboardMarkup` с
  парой «Подтвердить / Отменить».
- **`upgrade_callback_data(...)` / `parse_upgrade_callback_data(...)`** —
  кодирование/декодирование `callback_data`. Формат:
  ``"upgrade:<action>:<expected_cost_cm>"`` ≤ 64 байта. `action` — один
  из `confirm / cancel`.

`expected_cost_cm` зашит в callback_data: handler передаёт его обратно
в use-case как `UpgradeThicknessInput.expected_cost_cm`. Это защищает
от случая «balance.yaml перегружен между показом и нажатием
Подтвердить» — use-case бросит `ConcurrencyError`, а handler покажет
понятное сообщение.

Презентеры — чистые функции без I/O, тестируются изолированно.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Telegram callback_data hard-cap = 64 байта. Префикс + action +
# `expected_cost_cm` (до ~10 цифр) умещаются с большим запасом.
_CALLBACK_PREFIX: Final[str] = "upgrade"

UpgradeCallbackAction = Literal["confirm", "cancel"]
_VALID_ACTIONS: Final[frozenset[UpgradeCallbackAction]] = frozenset({"confirm", "cancel"})


@dataclass(frozen=True, slots=True)
class UpgradeCallbackData:
    """Распаршенный `callback_data` инлайн-кнопки `/upgrade`.

    `expected_cost_cm` — стоимость, которую UI показал пользователю.
    Use-case `UpgradeThickness` сверяется с актуальной стоимостью и
    бросает `ConcurrencyError` при расхождении. `0` для `cancel`-кнопки.
    """

    action: UpgradeCallbackAction
    expected_cost_cm: int


def render_upgrade_proposal(
    *,
    current_thickness: int,
    cost_cm: int,
    current_length_cm: int,
    min_after_spend_cm: int,
) -> str:
    """Карточка подтверждения «Прокачать с N до N+1?».

    Содержит текущий уровень, целевой уровень, стоимость и остаток
    после списания. Если у игрока не хватает длины — handler сам
    подменяет это сообщение через `render_upgrade_insufficient(...)`,
    кнопок не показывает.
    """
    next_level = current_thickness + 1
    remaining = current_length_cm - cost_cm
    return (
        "📐 Прокачка толщины\n"
        f"Текущий уровень: {current_thickness}\n"
        f"Целевой уровень: {next_level}\n"
        f"Стоимость: {cost_cm} см\n"
        f"У тебя: {current_length_cm} см\n"
        f"Останется: {remaining} см "
        f"(минимум по правилу 20 см: {min_after_spend_cm})"
    )


def render_upgrade_success(
    *,
    new_thickness: int,
    cost_cm: int,
    new_length_cm: int,
) -> str:
    """Подтверждение «Толщина прокачана» после успешного use-case-а."""
    return (
        f"✅ Толщина прокачана до {new_thickness}!\n"
        f"📏 Списано: {cost_cm} см\n"
        f"Осталось: {new_length_cm} см"
    )


def render_upgrade_insufficient(
    *,
    current_thickness: int,
    cost_cm: int,
    current_length_cm: int,
    deficit_cm: int,
    min_after_spend_cm: int,
) -> str:
    """Текст ответа при `InsufficientLengthError` (правило 20 см).

    Поясняет игроку, сколько ещё см нужно набрать, чтобы прокачаться.
    """
    next_level = current_thickness + 1
    return (
        f"❌ Недостаточно длины для прокачки до {next_level}.\n"
        f"Стоимость: {cost_cm} см\n"
        f"У тебя: {current_length_cm} см\n"
        f"Минимальный остаток: {min_after_spend_cm} см\n"
        f"Не хватает: {deficit_cm} см"
    )


RENDER_UPGRADE_CANCELLED: Final[str] = "Прокачка отменена."
RENDER_UPGRADE_RACE_RU: Final[str] = (
    "⚠️ Стоимость прокачки изменилась — открой /upgrade ещё раз, чтобы увидеть актуальную."
)


def build_upgrade_proposal_keyboard(*, expected_cost_cm: int) -> InlineKeyboardMarkup:
    """Инлайн-клавиатура «Подтвердить / Отменить» под карточкой /upgrade."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Подтвердить ({expected_cost_cm} см)",
                    callback_data=upgrade_callback_data("confirm", expected_cost_cm),
                ),
                InlineKeyboardButton(
                    text="Отменить",
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
    "RENDER_UPGRADE_CANCELLED",
    "RENDER_UPGRADE_RACE_RU",
    "UpgradeCallbackAction",
    "UpgradeCallbackData",
    "build_upgrade_proposal_keyboard",
    "parse_upgrade_callback_data",
    "render_upgrade_insufficient",
    "render_upgrade_proposal",
    "render_upgrade_success",
    "upgrade_callback_data",
]
