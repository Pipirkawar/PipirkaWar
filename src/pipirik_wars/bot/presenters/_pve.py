"""Общий презентер PvE-локаций с ±-исходами (горы и данжон, Спринт 3.1-E, ГДД §8.2).

Mountains и dungeon идентичны структурно (cooldown, ±-исход, drops, без
NameDrop), отличаются только балансовыми числами и префиксом локали.
Поэтому презентер общий — `PvePresenter(bundle, kind)` — а тонкие
обёртки `MountainsPresenter` / `DungeonPresenter` нужны только чтобы
явно указать `PveLocationKind` и держать публичный API близким к
`ForestPresenter`.

Префикс ключей локали = `kind.value` («mountains» / «dungeon»). Префикс
`callback_data` тот же. Это держит локализацию и сериализацию событий
синхронными: одна точка истины (`PveLocationKind`) — нет дрейфа между
локалями и handler-ами.

Скроллы заточки в карточке возврата **не показываются**: они не
персистятся в `MountainRun`/`DungeonRun.starting(outcome=)` (Спринт 3.1-D
by design — `Run.starting(outcome=)` копирует только `outcome.drops`,
см. `domain/pve/entities.PveScrollDrop`). UX скроллов появится в
Спринте 3.4 вместе с use-cases применения.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.dungeon import DungeonRunFinished
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.mountains import MountainRunFinished
from pipirik_wars.bot.presenters.profile import title_message_key
from pipirik_wars.domain.balance.config import Rarity
from pipirik_wars.domain.dungeon import DungeonRun
from pipirik_wars.domain.mountains import MountainRun
from pipirik_wars.domain.player import DisplayName, Player, PlayerName, Title
from pipirik_wars.domain.pve import PveItemDrop, PveLocationKind

# `mountains:equip_item:<run_id>:<idx>` ≤ 64 байт даже для 19-значных
# `run_id` и индексов до 99 — Telegram callback_data hard-cap.
PveCallbackAction = Literal["equip_item", "drop_item"]
_VALID_ACTIONS: Final[frozenset[PveCallbackAction]] = frozenset({"equip_item", "drop_item"})

_RARITY_KEY: Final[dict[Rarity, MessageKey]] = {
    Rarity.COMMON: MessageKey("forest-rarity-common"),
    Rarity.RARE: MessageKey("forest-rarity-rare"),
    Rarity.EPIC: MessageKey("forest-rarity-epic"),
}


@dataclass(frozen=True, slots=True)
class PveCallbackData:
    """Распаршенный `callback_data` инлайн-кнопки PvE-локации.

    `kind` — `PveLocationKind.MOUNTAINS` / `PveLocationKind.DUNGEON`,
    определяет, какому router-у адресован callback. `run_id` — id
    записи `mountain_runs`/`dungeon_runs`. `drop_idx` — позиция дропа
    в `run.drops` (handler сейчас использует только для idempotent
    «надеть/выбросить» placeholder-toast-ов, реальная экипировка — Спринт 3.4).
    """

    kind: PveLocationKind
    action: PveCallbackAction
    run_id: int
    drop_idx: int


def pve_callback_data(
    *, kind: PveLocationKind, action: PveCallbackAction, run_id: int, drop_idx: int
) -> str:
    """Сериализовать `callback_data` PvE-кнопки.

    Формат: `<kind>:<action>:<run_id>:<drop_idx>` (стабилен между
    релизами — handler-ы парсят `parse_pve_callback_data`).
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown PvE callback action: {action!r}")
    if run_id <= 0:
        raise ValueError(f"PvE callback run_id must be > 0, got {run_id}")
    if drop_idx < 0:
        raise ValueError(f"PvE callback drop_idx must be >= 0, got {drop_idx}")
    return f"{kind.value}:{action}:{run_id}:{drop_idx}"


def parse_pve_callback_data(data: str) -> PveCallbackData:
    """Распарсить `callback_data` PvE-кнопки. На любой мусор — `ValueError`."""
    parts = data.split(":")
    if len(parts) != 4:
        raise ValueError(f"PvE callback_data must be 4-part, got {data!r}")
    kind_raw, action_raw, run_id_raw, drop_idx_raw = parts
    try:
        kind = PveLocationKind(kind_raw)
    except ValueError as exc:
        raise ValueError(f"unknown PvE kind: {kind_raw!r}") from exc
    if action_raw not in _VALID_ACTIONS:
        raise ValueError(f"unknown PvE action: {action_raw!r}")
    try:
        run_id = int(run_id_raw)
        drop_idx = int(drop_idx_raw)
    except ValueError as exc:
        raise ValueError(f"PvE callback ints malformed in {data!r}") from exc
    if run_id <= 0 or drop_idx < 0:
        raise ValueError(f"PvE callback ints out of range in {data!r}")
    # mypy: action_raw уже проверен на принадлежность _VALID_ACTIONS.
    return PveCallbackData(
        kind=kind,
        action=action_raw,  # type: ignore[arg-type]
        run_id=run_id,
        drop_idx=drop_idx,
    )


class PvePresenter:
    """Локализованный рендер ответов `/mountains` и `/dungeon` через `IMessageBundle`.

    Используется handler-ом и notifier-ом (TelegramMountainFinishNotifier /
    TelegramDungeonFinishNotifier) — оба зовут одну и ту же
    `finished(...)` / `finish_keyboard(...)`.
    """

    __slots__ = ("_bundle", "_kind")

    def __init__(self, *, bundle: IMessageBundle, kind: PveLocationKind) -> None:
        self._bundle = bundle
        self._kind = kind

    @property
    def kind(self) -> PveLocationKind:
        return self._kind

    # --- Команда `/mountains` / `/dungeon` ---

    def group(self, *, locale: Locale) -> str:
        return self._bundle.format(self._key("group"), locale=locale)

    def other(self, *, locale: Locale) -> str:
        return self._bundle.format(self._key("other"), locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(self._key("not-registered"), locale=locale)

    def already_in(self, *, locale: Locale) -> str:
        return self._bundle.format(self._key("already-in"), locale=locale)

    def requirement_thickness(self, *, required: int, actual: int, locale: Locale) -> str:
        """Сообщение «нужен уровень толщины ≥ N» (ГДД §8 — гейт входа)."""
        return self._bundle.format(
            self._key("requirement-thickness"),
            locale=locale,
            required=required,
            actual=actual,
        )

    def requirement_length(self, *, required_cm: int, actual_cm: int, locale: Locale) -> str:
        """Сообщение «нужно ≥ N см длины» (ГДД §3.1 — Правило 20 см)."""
        return self._bundle.format(
            self._key("requirement-length"),
            locale=locale,
            required_cm=required_cm,
            actual_cm=actual_cm,
        )

    def started(
        self,
        *,
        player: Player,
        display_name: DisplayName,
        cooldown_minutes: int,
        locale: Locale,
    ) -> str:
        """Сообщение «ушёл в горы/данжон» (ГДД §8.2). Формат `[Титул] [Название] [Имя]`."""
        nick = self._render_full_nick(
            title=player.title,
            display_name=display_name,
            name=player.name,
            locale=locale,
        )
        return self._bundle.format(
            self._key("started"),
            locale=locale,
            nick=nick,
            cooldown_minutes=cooldown_minutes,
        )

    def started_fallback(self, *, cooldown_minutes: int, locale: Locale) -> str:
        """Fallback на случай, когда `GetProfile` не нашёл игрока сразу
        после старта похода. Без полного ника.
        """
        return self._bundle.format(
            self._key("started-fallback"),
            locale=locale,
            cooldown_minutes=cooldown_minutes,
        )

    # --- Сообщение «вернулся из гор/данжона» ---

    def finished(
        self,
        *,
        result: MountainRunFinished | DungeonRunFinished,
        display_name_after: DisplayName,
        locale: Locale,
    ) -> str:
        """Полный текст сообщения «вернулся» (ГДД §8.2).

        Формат:
        - заголовок (`<prefix>-finished-header`)
        - длина (`<prefix>-finished-length-gain` / `-loss` / `-zero`)
        - 0..N строк дропа (`<prefix>-finished-item-found`)

        Branch-name намеренно не показываем — это машинный идентификатор
        ветки `balance.yaml`, для UX он не несёт ценности (игрок видит
        и так — длина выросла или упала, плюс появился дроп).
        """
        run = result.run
        before = result.player_before
        after = result.player_after
        nick = self._render_full_nick(
            title=after.title,
            display_name=display_name_after,
            name=after.name,
            locale=locale,
        )
        lines: list[str] = [
            self._bundle.format(self._key("finished-header"), locale=locale, nick=nick),
            self._render_length_line(
                length_delta_cm=run.length_delta_cm,
                length_before_cm=before.length.cm,
                length_after_cm=after.length.cm,
                locale=locale,
            ),
        ]
        for drop in run.drops:
            lines.append(
                self._render_drop_line(drop=drop, locale=locale),
            )
        return "\n".join(lines)

    def finish_keyboard(
        self,
        result: MountainRunFinished | DungeonRunFinished,
        *,
        locale: Locale,
    ) -> InlineKeyboardMarkup | None:
        """Инлайн-клавиатура для сообщения «вернулся»: пара
        «Надеть / Выбросить» × N для каждого дропа.

        `None`, если дропов не было (ничего нажимать). `callback_data`
        стабилен и не зависит от локали (см. `pve_callback_data`).
        """
        run = result.run
        if not run.drops:
            return None
        assert run.id is not None
        rows: list[list[InlineKeyboardButton]] = []
        for idx, _drop in enumerate(run.drops):
            rows.append(
                [
                    InlineKeyboardButton(
                        text=self._bundle.format(self._key("button-equip"), locale=locale),
                        callback_data=pve_callback_data(
                            kind=self._kind,
                            action="equip_item",
                            run_id=run.id,
                            drop_idx=idx,
                        ),
                    ),
                    InlineKeyboardButton(
                        text=self._bundle.format(
                            self._key("button-drop-item"),
                            locale=locale,
                        ),
                        callback_data=pve_callback_data(
                            kind=self._kind,
                            action="drop_item",
                            run_id=run.id,
                            drop_idx=idx,
                        ),
                    ),
                ]
            )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    # --- Toast-ы для callback-ответов ---

    def toast_item_equipped_placeholder(self, *, locale: Locale) -> str:
        return self._bundle.format(self._key("toast-item-equipped-placeholder"), locale=locale)

    def toast_item_dropped(self, *, locale: Locale) -> str:
        return self._bundle.format(self._key("toast-item-dropped"), locale=locale)

    def toast_foreign_button(self, *, locale: Locale) -> str:
        return self._bundle.format(self._key("toast-foreign-button"), locale=locale)

    def toast_run_not_found(self, *, locale: Locale) -> str:
        return self._bundle.format(self._key("toast-run-not-found"), locale=locale)

    def toast_drop_mismatch(self, *, locale: Locale) -> str:
        return self._bundle.format(self._key("toast-drop-mismatch"), locale=locale)

    # --- Хелперы ---

    def _key(self, suffix: str) -> MessageKey:
        return MessageKey(f"{self._kind.value}-{suffix}")

    def _render_length_line(
        self,
        *,
        length_delta_cm: int,
        length_before_cm: int,
        length_after_cm: int,
        locale: Locale,
    ) -> str:
        if length_delta_cm > 0:
            return self._bundle.format(
                self._key("finished-length-gain"),
                locale=locale,
                length_delta_cm=length_delta_cm,
                length_before_cm=length_before_cm,
                length_after_cm=length_after_cm,
            )
        if length_delta_cm < 0:
            return self._bundle.format(
                self._key("finished-length-loss"),
                locale=locale,
                length_delta_abs_cm=-length_delta_cm,
                length_before_cm=length_before_cm,
                length_after_cm=length_after_cm,
            )
        return self._bundle.format(
            self._key("finished-length-zero"),
            locale=locale,
            length_before_cm=length_before_cm,
        )

    def _render_drop_line(self, *, drop: PveItemDrop, locale: Locale) -> str:
        rarity = self._bundle.format(_RARITY_KEY[drop.item.rarity], locale=locale)
        return self._bundle.format(
            self._key("finished-item-found"),
            locale=locale,
            item_name=drop.item.display_name,
            rarity=rarity,
        )

    def _render_full_nick(
        self,
        *,
        title: Title | None,
        display_name: DisplayName,
        name: PlayerName | None,
        locale: Locale,
    ) -> str:
        """Собрать «полный ник»: `[Локализованный титул] [Название] [Имя]`."""
        parts: list[str] = []
        if title is not None:
            parts.append(self._bundle.format(title_message_key(title), locale=locale))
        parts.append(display_name.value)
        if name is not None:
            parts.append(name.value)
        return " ".join(parts)


def is_pve_callback(data: str | None) -> bool:
    """Filter helper — это PvE callback (mountains: или dungeon:)?

    Используется handler-ами `mountains.py` / `dungeon.py` через
    `F.data.startswith(...)`-фильтры. Без него aiogram прокинет любой
    callback с подходящим префиксом, в т. ч. forest-ные.
    """
    if data is None:
        return False
    return data.startswith("mountains:") or data.startswith("dungeon:")


# Локальные алиасы для совместимости с типизированными `MountainRun` /
# `DungeonRun` — через объединённые типы handler-ы пишут единообразно.
PveRun = MountainRun | DungeonRun


__all__ = [
    "PveCallbackAction",
    "PveCallbackData",
    "PvePresenter",
    "PveRun",
    "is_pve_callback",
    "parse_pve_callback_data",
    "pve_callback_data",
]
