"""Презентеры сообщений похода в лес (Спринт 1.3.D, ГДД §8.2).

Тонкий слой между use-case-ами `StartForestRun` / `FinishForestRun` и
Telegram-handler-ом / нотификатором. Здесь живут:

- **`render_forest_started(...)`** — текст «🌲 N ушёл в лес на M минут»
  для ответа на `/forest` (ПД §1.3.2 / ГДД §8.2).
- **`render_forest_finished(...)`** — текст «🌲 N вернулся из леса» с
  начислением длины и описанием находки (ПД §1.3.2 / ГДД §8.2).
- **`build_finish_keyboard(...)`** — `InlineKeyboardMarkup` для дропа.
  Только для случаев, когда у игрока есть выбор: `ItemDrop` (надеть/
  выбросить) и `NameDrop` при уже имеющемся имени (заменить/выбросить).
  `NoDrop` и `NameDrop`-auto-apply на новичке клавиатуры не получают.
- **`forest_callback_data(...)`** / **`parse_forest_callback_data(...)`**
  — кодирование/декодирование `callback_data` инлайн-кнопок. Формат:
  `"forest:<action>:<run_id>"` ≤ 64 байт (Telegram-лимит). `action` —
  один из `equip_item / drop_item / apply_name / drop_name`.

Презентер не делает I/O и не зависит от инфраструктуры — берёт
доменные сущности (`ForestRun` / `ForestRunFinished` / `Player` /
`DisplayName`) и возвращает строки + клавиатуру, готовые к отправке.

Полный ник `[Титул] [Название] [Имя]` берём из существующего
`render_full_nick(...)` (Спринт 1.1.E) — тот же формат, что и в
`/profile`-карточке.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.forest import ForestRunFinished
from pipirik_wars.bot.presenters.profile import render_full_nick
from pipirik_wars.domain.forest import (
    Drop,
    ItemDrop,
    NameDrop,
    NoDrop,
    Rarity,
)
from pipirik_wars.domain.player import DisplayName, Player

# Telegram callback_data hard-cap = 64 байта; наш формат вместе с самым
# длинным action ("apply_name") и `int`-ом до 19 цифр умещается с запасом.
_CALLBACK_PREFIX: Final[str] = "forest"

ForestCallbackAction = Literal[
    "equip_item",
    "drop_item",
    "apply_name",
    "drop_name",
]
_VALID_ACTIONS: Final[frozenset[ForestCallbackAction]] = frozenset(
    {"equip_item", "drop_item", "apply_name", "drop_name"}
)

# Локализация редкостей для UI «Нашёл: <предмет> [<редкость>]» (ГДД §8.2).
_RARITY_RU: Final[dict[Rarity, str]] = {
    Rarity.COMMON: "обычный",
    Rarity.RARE: "редкий",
    Rarity.EPIC: "эпический",
}


@dataclass(frozen=True, slots=True)
class ForestCallbackData:
    """Распаршенный `callback_data` инлайн-кнопки леса.

    `run_id` — id записи `forest_runs`, по которому handler-ы достают
    игрока и `Drop` (`run.drop` уже сохранён на старте — Спринт 1.3.B).
    """

    action: ForestCallbackAction
    run_id: int


def render_forest_started(
    *,
    player: Player,
    display_name: DisplayName,
    cooldown_minutes: int,
) -> str:
    """Сообщение «ушёл в лес» (ПД §1.3.2 / ГДД §8.2).

    Формат:
        🌲 <Полный ник> ушёл в лес на <N> минут...

    Полный ник — `[Титул] [Название] [Имя]` с пропуском `None`-частей
    (Спринт 1.1.E, см. `render_full_nick`). Для свежезарегистрированного
    игрока получается «Пипирик» — это by design.
    """
    nick = render_full_nick(
        title=player.title,
        display_name=display_name,
        name=player.name,
    )
    return f"🌲 {nick} ушёл в лес на {cooldown_minutes} минут..."


def render_forest_finished(
    *,
    result: ForestRunFinished,
    display_name_after: DisplayName,
) -> str:
    """Сообщение «вернулся из леса» (ПД §1.3.2 / ГДД §8.2).

    Формат:
        🌲 <Полный ник> вернулся из леса!
        📏 Длина: +5 см (было 47, стало 52)
        🎩 Нашёл: <Имя предмета> [<редкость>]
           → Надеть | Выбросить    (для ItemDrop)

    `display_name_after` — пересчитанное название по новой длине игрока
    (после применения `length_delta_cm`). Для `NameDrop`-auto-apply мы
    также показываем выданное имя в строке-уведомлении.
    """
    after = result.player_after
    before = result.player_before
    nick = render_full_nick(
        title=after.title,
        display_name=display_name_after,
        name=after.name,
    )
    lines: list[str] = [
        f"🌲 {nick} вернулся из леса!",
        (
            f"📏 Длина: +{result.run.length_delta_cm} см "
            f"(было {before.length.cm}, стало {after.length.cm})"
        ),
    ]

    if result.granted_title:
        # ГДД §8.2: первое возвращение из леса → титул «Новичок».
        lines.append("🎖 Получен титул: Новичок")

    drop = result.run.drop
    if isinstance(drop, NoDrop):
        # Лес ничего не подарил — длина уже учтена выше.
        return "\n".join(lines)
    if isinstance(drop, ItemDrop):
        rarity_ru = _RARITY_RU[drop.item.rarity]
        lines.append(f"🎩 Нашёл: {drop.item.display_name} [{rarity_ru}]")
        return "\n".join(lines)
    if isinstance(drop, NameDrop):
        if result.granted_name:
            # Имя выдано автоматически (новичок без имени, см. 1.3.C /
            # `FinishForestRun`).
            lines.append(f"🪪 Получено имя: {drop.name.value}")
        else:
            # У игрока уже есть имя — предлагаем заменить или выбросить.
            lines.append(f"🪪 Нашёл имя: {drop.name.value}")
        return "\n".join(lines)
    # mypy --strict требует исчерпывающего раскрытия Drop.
    raise AssertionError(f"unknown drop variant: {drop!r}")


def build_finish_keyboard(result: ForestRunFinished) -> InlineKeyboardMarkup | None:
    """Инлайн-клавиатура для сообщения «вернулся из леса».

    Возвращает:
    - `None` — если кнопок не нужно (`NoDrop` или `NameDrop`-auto-apply
      на новичке без имени).
    - `InlineKeyboardMarkup` с парой кнопок «Надеть / Выбросить» — для
      `ItemDrop` (1.3.6).
    - `InlineKeyboardMarkup` с парой кнопок «Заменить / Выбросить» — для
      `NameDrop`, когда `result.granted_name is False` (у игрока уже
      есть имя; ГДД §2.5 / 1.3.7).
    """
    run = result.run
    assert run.id is not None  # FinishForestRun возвращает запись с id
    drop = run.drop

    if isinstance(drop, NoDrop):
        return None
    if isinstance(drop, ItemDrop):
        return _build_item_keyboard(run_id=run.id)
    if isinstance(drop, NameDrop):
        if result.granted_name:
            # Имя уже применено автоматически — кнопок не нужно.
            return None
        return _build_name_replacement_keyboard(run_id=run.id)
    raise AssertionError(f"unknown drop variant: {drop!r}")


def _build_item_keyboard(*, run_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Надеть",
                    callback_data=forest_callback_data("equip_item", run_id),
                ),
                InlineKeyboardButton(
                    text="Выбросить",
                    callback_data=forest_callback_data("drop_item", run_id),
                ),
            ],
        ]
    )


def _build_name_replacement_keyboard(*, run_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Заменить",
                    callback_data=forest_callback_data("apply_name", run_id),
                ),
                InlineKeyboardButton(
                    text="Выбросить",
                    callback_data=forest_callback_data("drop_name", run_id),
                ),
            ],
        ]
    )


def forest_callback_data(action: ForestCallbackAction, run_id: int) -> str:
    """Сериализовать `callback_data` для инлайн-кнопки леса.

    Формат: ``"forest:<action>:<run_id>"``. Telegram-лимит — 64 байта;
    самый длинный вариант (`forest:apply_name:<19digits>`) укладывается
    в 33 байта.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown forest callback action: {action!r}")
    if run_id <= 0:
        raise ValueError(f"forest callback run_id must be positive, got {run_id}")
    return f"{_CALLBACK_PREFIX}:{action}:{run_id}"


def parse_forest_callback_data(raw: str) -> ForestCallbackData:
    """Распарсить `callback_data`. Бросает `ValueError` при несоответствии.

    Handler ловит `ValueError` и игнорирует «битые» нажатия (например,
    после future-перевыпуска формата кнопок). Это не ошибка пользователя
    и не повод спамить ему сообщением.
    """
    parts = raw.split(":")
    if len(parts) != 3 or parts[0] != _CALLBACK_PREFIX:
        raise ValueError(f"invalid forest callback_data: {raw!r}")
    _, action_raw, run_id_raw = parts
    if action_raw not in _VALID_ACTIONS:
        raise ValueError(f"unknown forest callback action: {action_raw!r}")
    try:
        run_id = int(run_id_raw)
    except ValueError as exc:
        raise ValueError(f"invalid forest callback run_id: {run_id_raw!r}") from exc
    if run_id <= 0:
        raise ValueError(f"forest callback run_id must be positive, got {run_id}")
    # mypy: после проверки `action_raw in _VALID_ACTIONS` мы знаем,
    # что это именно `ForestCallbackAction`, но Literal-сужение через
    # `in frozenset` mypy не делает — поэтому отдельная проверка ниже.
    return ForestCallbackData(
        action=_assert_action(action_raw),
        run_id=run_id,
    )


def _assert_action(raw: str) -> ForestCallbackAction:
    """Сужает `str` → `ForestCallbackAction` после проверки членства."""
    if raw == "equip_item":
        return "equip_item"
    if raw == "drop_item":
        return "drop_item"
    if raw == "apply_name":
        return "apply_name"
    if raw == "drop_name":
        return "drop_name"
    raise AssertionError(f"unreachable: action {raw!r} not in _VALID_ACTIONS")


def localized_rarity(rarity: Rarity) -> str:
    """Маппинг доменного `Rarity` → русская строка для UI."""
    return _RARITY_RU[rarity]


def has_finish_keyboard(drop: Drop, *, granted_name: bool) -> bool:
    """Хелпер для тестов: ожидает ли клавиатуру при таком дропе?"""
    if isinstance(drop, NoDrop):
        return False
    if isinstance(drop, ItemDrop):
        return True
    if isinstance(drop, NameDrop):
        return not granted_name
    raise AssertionError(f"unknown drop variant: {drop!r}")


__all__ = [
    "ForestCallbackAction",
    "ForestCallbackData",
    "build_finish_keyboard",
    "forest_callback_data",
    "has_finish_keyboard",
    "localized_rarity",
    "parse_forest_callback_data",
    "render_forest_finished",
    "render_forest_started",
]
