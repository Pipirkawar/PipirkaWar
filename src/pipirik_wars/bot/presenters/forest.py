"""Презентеры команды `/forest` (Спринт 1.3.D → 1.5.E, ГДД §8.2).

С 1.5.E переехал на `IMessageBundle`: класс `ForestPresenter` собирает
локализованные ответы handler-а (`/forest` и инлайн-кнопок) и нотификатора
(«вернулся из леса»). Pure-функции для `callback_data` оставлены как
есть — Telegram-`callback_data` не зависит от локали (см. ниже).

Презентер отвечает за:

1. **Локализацию** через `IMessageBundle`: ключи `forest-*` в
   `locales/{ru,en}.ftl`. Подписи кнопок, toast-ы, заголовки и
   строки сообщений — всё проходит через bundle.
2. **Сборку «полного ника»** (`[Локализованный титул] [Название] [Имя]`) —
   локализованное имя титула берётся из bundle через
   `profile.title_message_key(...)`, остальные части — из домена.
3. **Сборку клавиатур** — `finish_keyboard(...)` отдаёт
   `InlineKeyboardMarkup` с локализованными подписями. `callback_data`
   стабилен и не зависит от локали (см. `forest_callback_data`).

Pure-функции `forest_callback_data` / `parse_forest_callback_data` /
`has_finish_keyboard` — без зависимостей от bundle, оставлены вне
класса.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.forest import ForestRunFinished
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.bot.presenters.profile import title_message_key
from pipirik_wars.domain.forest import (
    Drop,
    ForestLogTemplate,
    ItemDrop,
    NameDrop,
    NoDrop,
    Rarity,
)
from pipirik_wars.domain.player import DisplayName, Player, PlayerName, Title

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

_KEY_GROUP: Final[MessageKey] = MessageKey("forest-group")
_KEY_OTHER: Final[MessageKey] = MessageKey("forest-other")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("forest-not-registered")
_KEY_ALREADY_IN: Final[MessageKey] = MessageKey("forest-already-in")
_KEY_STARTED: Final[MessageKey] = MessageKey("forest-started")
_KEY_STARTED_FALLBACK: Final[MessageKey] = MessageKey("forest-started-fallback")
_KEY_FINISHED_HEADER: Final[MessageKey] = MessageKey("forest-finished-header")
_KEY_FINISHED_LENGTH: Final[MessageKey] = MessageKey("forest-finished-length")
_KEY_FLAVOUR_DELTA: Final[MessageKey] = MessageKey("forest-flavour-delta")
_KEY_FINISHED_TITLE_GRANTED: Final[MessageKey] = MessageKey("forest-finished-title-granted")
_KEY_FINISHED_ITEM_FOUND: Final[MessageKey] = MessageKey("forest-finished-item-found")
_KEY_FINISHED_NAME_GRANTED: Final[MessageKey] = MessageKey("forest-finished-name-granted")
_KEY_FINISHED_NAME_FOUND: Final[MessageKey] = MessageKey("forest-finished-name-found")

_KEY_BUTTON_EQUIP: Final[MessageKey] = MessageKey("forest-button-equip")
_KEY_BUTTON_DROP_ITEM: Final[MessageKey] = MessageKey("forest-button-drop-item")
_KEY_BUTTON_REPLACE_NAME: Final[MessageKey] = MessageKey("forest-button-replace-name")
_KEY_BUTTON_DROP_NAME: Final[MessageKey] = MessageKey("forest-button-drop-name")

_KEY_TOAST_NAME_APPLIED: Final[MessageKey] = MessageKey("forest-toast-name-applied")
_KEY_TOAST_NAME_ALREADY_APPLIED: Final[MessageKey] = MessageKey("forest-toast-name-already-applied")
_KEY_TOAST_NAME_DROPPED: Final[MessageKey] = MessageKey("forest-toast-name-dropped")
_KEY_TOAST_ITEM_DROPPED: Final[MessageKey] = MessageKey("forest-toast-item-dropped")
_KEY_TOAST_ITEM_EQUIPPED_PLACEHOLDER: Final[MessageKey] = MessageKey(
    "forest-toast-item-equipped-placeholder"
)
_KEY_TOAST_FOREIGN_BUTTON: Final[MessageKey] = MessageKey("forest-toast-foreign-button")
_KEY_TOAST_RUN_NOT_FOUND: Final[MessageKey] = MessageKey("forest-toast-run-not-found")
_KEY_TOAST_DROP_MISMATCH: Final[MessageKey] = MessageKey("forest-toast-drop-mismatch")
_KEY_TOAST_PLAYER_NOT_FOUND: Final[MessageKey] = MessageKey("forest-toast-player-not-found")

# Маппинг доменного `Rarity` → ключ `forest-rarity-*` в bundle.
_RARITY_KEY: Final[dict[Rarity, MessageKey]] = {
    Rarity.COMMON: MessageKey("forest-rarity-common"),
    Rarity.RARE: MessageKey("forest-rarity-rare"),
    Rarity.EPIC: MessageKey("forest-rarity-epic"),
}


@dataclass(frozen=True, slots=True)
class ForestCallbackData:
    """Распаршенный `callback_data` инлайн-кнопки леса.

    `run_id` — id записи `forest_runs`, по которому handler-ы достают
    игрока и `Drop` (`run.drop` уже сохранён на старте — Спринт 1.3.B).
    """

    action: ForestCallbackAction
    run_id: int


class ForestPresenter:
    """Локализованный рендер ответов `/forest` через `IMessageBundle`.

    Используется и handler-ом (для немедленных ответов в чат на команду
    `/forest` и инлайн-кнопки), и нотификатором (для отправки сообщения
    «вернулся из леса» из background-job-а APScheduler-а).
    """

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- Команда `/forest` ---

    def group(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GROUP, locale=locale)

    def other(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_OTHER, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    def already_in(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_ALREADY_IN, locale=locale)

    def started(
        self,
        *,
        player: Player,
        display_name: DisplayName,
        cooldown_minutes: int,
        locale: Locale,
    ) -> str:
        """Сообщение «ушёл в лес» (ГДД §8.2). Формат `[Титул] [Название] [Имя]`."""
        nick = self._render_full_nick(
            title=player.title,
            display_name=display_name,
            name=player.name,
            locale=locale,
        )
        return self._bundle.format(
            _KEY_STARTED,
            locale=locale,
            nick=nick,
            cooldown_minutes=cooldown_minutes,
        )

    def started_fallback(self, *, cooldown_minutes: int, locale: Locale) -> str:
        """Fallback на случай, когда `GetProfile` не нашёл игрока сразу
        после `StartForestRun`. Без полного ника.
        """
        return self._bundle.format(
            _KEY_STARTED_FALLBACK,
            locale=locale,
            cooldown_minutes=cooldown_minutes,
        )

    # --- Сообщение «вернулся из леса» ---

    def finished(
        self,
        *,
        result: ForestRunFinished,
        display_name_after: DisplayName,
        locale: Locale,
        flavor_template: ForestLogTemplate | None = None,
    ) -> str:
        """Полный текст сообщения «вернулся из леса» (ГДД §8.2).

        Собирается построчно: заголовок + длина + (титул) + (находка)
        + (flavour-строка из каталога 1.5.G).

        `flavor_template` (опционально, ПД 1.5.3) — выбранный наружным
        кодом шаблон забавного лога. Презентер сам подставляет
        плейсхолдеры `{user}` (полный ник «Титул Название Имя») и
        `{delta}` (`+N см` / `+N cm` через bundle-ключ
        `forest-flavour-delta`).
        """
        after = result.player_after
        before = result.player_before
        nick = self._render_full_nick(
            title=after.title,
            display_name=display_name_after,
            name=after.name,
            locale=locale,
        )
        lines: list[str] = [
            self._bundle.format(_KEY_FINISHED_HEADER, locale=locale, nick=nick),
            self._bundle.format(
                _KEY_FINISHED_LENGTH,
                locale=locale,
                length_delta_cm=result.run.length_delta_cm,
                length_before_cm=before.length.cm,
                length_after_cm=after.length.cm,
            ),
        ]
        if flavor_template is not None:
            lines.append(
                self._render_flavor(
                    template=flavor_template,
                    nick=nick,
                    length_delta_cm=result.run.length_delta_cm,
                    locale=locale,
                )
            )
        if result.granted_title:
            lines.append(self._bundle.format(_KEY_FINISHED_TITLE_GRANTED, locale=locale))

        drop = result.run.drop
        if isinstance(drop, NoDrop):
            return "\n".join(lines)
        if isinstance(drop, ItemDrop):
            rarity = self._bundle.format(_RARITY_KEY[drop.item.rarity], locale=locale)
            lines.append(
                self._bundle.format(
                    _KEY_FINISHED_ITEM_FOUND,
                    locale=locale,
                    item_name=drop.item.display_name,
                    rarity=rarity,
                )
            )
            return "\n".join(lines)
        if isinstance(drop, NameDrop):
            if result.granted_name:
                lines.append(
                    self._bundle.format(
                        _KEY_FINISHED_NAME_GRANTED,
                        locale=locale,
                        name=drop.name.value,
                    )
                )
            else:
                lines.append(
                    self._bundle.format(
                        _KEY_FINISHED_NAME_FOUND,
                        locale=locale,
                        name=drop.name.value,
                    )
                )
            return "\n".join(lines)
        # mypy --strict требует исчерпывающего раскрытия Drop.
        raise AssertionError(f"unknown drop variant: {drop!r}")

    def finish_keyboard(
        self,
        result: ForestRunFinished,
        *,
        locale: Locale,
    ) -> InlineKeyboardMarkup | None:
        """Инлайн-клавиатура для сообщения «вернулся из леса» с
        локализованными подписями кнопок. `callback_data` — invariant.

        Возвращает:
        - `None` — если кнопок не нужно (`NoDrop` или `NameDrop`-auto-apply
          на новичке без имени).
        - `InlineKeyboardMarkup` с парой кнопок «Надеть / Выбросить» — для
          `ItemDrop` (1.3.6).
        - `InlineKeyboardMarkup` с парой кнопок «Заменить / Выбросить» — для
          `NameDrop`, когда `result.granted_name is False`.
        """
        run = result.run
        assert run.id is not None
        drop = run.drop
        if isinstance(drop, NoDrop):
            return None
        if isinstance(drop, ItemDrop):
            return InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=self._bundle.format(_KEY_BUTTON_EQUIP, locale=locale),
                            callback_data=forest_callback_data("equip_item", run.id),
                        ),
                        InlineKeyboardButton(
                            text=self._bundle.format(_KEY_BUTTON_DROP_ITEM, locale=locale),
                            callback_data=forest_callback_data("drop_item", run.id),
                        ),
                    ],
                ]
            )
        if isinstance(drop, NameDrop):
            if result.granted_name:
                return None
            return InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=self._bundle.format(_KEY_BUTTON_REPLACE_NAME, locale=locale),
                            callback_data=forest_callback_data("apply_name", run.id),
                        ),
                        InlineKeyboardButton(
                            text=self._bundle.format(_KEY_BUTTON_DROP_NAME, locale=locale),
                            callback_data=forest_callback_data("drop_name", run.id),
                        ),
                    ],
                ]
            )
        raise AssertionError(f"unknown drop variant: {drop!r}")

    # --- Toast-ы для callback-ответов ---

    def toast_name_applied(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_NAME_APPLIED, locale=locale)

    def toast_name_already_applied(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_NAME_ALREADY_APPLIED, locale=locale)

    def toast_name_dropped(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_NAME_DROPPED, locale=locale)

    def toast_item_dropped(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_ITEM_DROPPED, locale=locale)

    def toast_item_equipped_placeholder(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_ITEM_EQUIPPED_PLACEHOLDER, locale=locale)

    def toast_foreign_button(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_FOREIGN_BUTTON, locale=locale)

    def toast_run_not_found(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_RUN_NOT_FOUND, locale=locale)

    def toast_drop_mismatch(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_DROP_MISMATCH, locale=locale)

    def toast_player_not_found(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_PLAYER_NOT_FOUND, locale=locale)

    # --- Хелперы ---

    def localized_rarity(self, rarity: Rarity, *, locale: Locale) -> str:
        """Локализованная редкость для UI «Нашёл: <предмет> [<редкость>]»."""
        return self._bundle.format(_RARITY_KEY[rarity], locale=locale)

    def _render_full_nick(
        self,
        *,
        title: Title | None,
        display_name: DisplayName,
        name: PlayerName | None,
        locale: Locale,
    ) -> str:
        """Собрать «полный ник» с локализованным именем титула.

        Формат `[Локализованный титул] [Название] [Имя]` с пропуском
        `None`-частей. Для новичка без титула и имени → только название.
        """
        parts: list[str] = []
        if title is not None:
            parts.append(self._bundle.format(title_message_key(title), locale=locale))
        parts.append(display_name.value)
        if name is not None:
            parts.append(name.value)
        return " ".join(parts)

    def _render_flavor(
        self,
        *,
        template: ForestLogTemplate,
        nick: str,
        length_delta_cm: int,
        locale: Locale,
    ) -> str:
        """Подставить плейсхолдеры в шаблон забавного лога (ГДД §15).

        Поддерживаемые плейсхолдеры: `{user}` (полный ник),
        `{delta}` (`+N см` / `+N cm` — берётся из bundle-ключа
        `forest-flavour-delta`).

        Шаблон может содержать оба плейсхолдера, один из них, или ни
        одного — `str.format` молча игнорирует unused-keys.
        """
        delta = self._bundle.format(
            _KEY_FLAVOUR_DELTA,
            locale=locale,
            length_delta_cm=length_delta_cm,
        )
        try:
            return template.text.format(user=nick, delta=delta)
        except (KeyError, IndexError, ValueError):
            # Defensive: если в шаблоне кривой плейсхолдер (`{usr}` /
            # позиционный) — отдаём сырой текст, чтобы не сломать
            # сообщение игрока. Это invariant-нарушение каталога, должно
            # ловиться в integration-тесте на JSON-файле.
            return template.text


def forest_callback_data(action: ForestCallbackAction, run_id: int) -> str:
    """Сериализовать `callback_data` для инлайн-кнопки леса.

    Формат: ``"forest:<action>:<run_id>"``. Telegram-лимит — 64 байта;
    самый длинный вариант (`forest:apply_name:<19digits>`) укладывается
    в 33 байта. Не зависит от локали (см. ниже).

    `callback_data` — invariant-формат: пользователь может переключить
    локаль между показом сообщения и кликом, и handler всё равно должен
    корректно распарсить нажатие. Локализуется только подпись кнопки
    (`InlineKeyboardButton.text`), а сам `callback_data` стабилен.
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
    "ForestPresenter",
    "forest_callback_data",
    "has_finish_keyboard",
    "parse_forest_callback_data",
]
