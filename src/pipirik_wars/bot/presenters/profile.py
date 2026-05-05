"""Презентер карточки персонажа `/profile` (Спринт 1.1.E → 1.5.C, ГДД §2.1/§2.2).

Тонкий слой между use-case-ом `GetProfile` и Telegram-handler-ом.
Не делает I/O, не зависит от инфраструктуры — берёт `ProfileView`
(содержит `Player` + рассчитанный `DisplayName`) и `Locale` из
middleware-а, а на выход отдаёт строку, готовую к отправке через
`message.answer(...)`.

В Спринте 1.5.C класс `ProfilePresenter` пришёл на смену чистым
функциям `render_profile_card` / `render_full_nick`: текст теперь
берётся не из hardcoded RU-констант, а из `IMessageBundle` по
ключам `profile-*` в `locales/{ru,en}.ftl`.

Из ГДД §2.1 формат «полного ника» — `[Титул] [Название] [Имя]`,
*пропуская* отсутствующие части (новичок без титула и без имени
показывается как `Пипирик`).

Карточка из ГДД §2.2:

    🏷 Ядрёный Бананчик Коляндр

    📏 Длина: 47 см
    📐 Толщина: 5

    🎽 Экипировка: пока пусто

В Спринте 1.1.E экипировки **ещё нет** — она появится в Спринте 1.3+
(дроп предметов из леса). Пока строка «Экипировка» либо опускается,
либо рендерится как «🎽 Экипировка: пока пусто», чтобы карточка не
вводила игрока в заблуждение и не выглядела «недозагруженной».

`render_full_nick` оставлен «совместимой» pure-функцией без
`IMessageBundle`: её до сих пор использует `bot/presenters/forest.py`
для рендера уведомлений после run-а. После миграции `/forest` на
презентер (Спринт 1.5.D) функция уйдёт.
"""

from __future__ import annotations

from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.player import ProfileView
from pipirik_wars.domain.player import DisplayName, PlayerName, Title

_KEY_GROUP: Final[MessageKey] = MessageKey("profile-group")
_KEY_OTHER: Final[MessageKey] = MessageKey("profile-other")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("profile-not-registered")
_KEY_CARD: Final[MessageKey] = MessageKey("profile-card")

# ГДД §2.4: сейчас определён только один титул `Title.NEWBIE`.
# Hardcoded RU-маппинг используется legacy-функцией `render_full_nick`,
# которую пока зовут `bot/presenters/forest.py` и `bot/presenters/top.py`.
# В `ProfilePresenter` титул берётся из `.ftl` через `IMessageBundle`.
_TITLE_RU: Final[dict[Title, str]] = {
    Title.NEWBIE: "Новичок",
}


def render_full_nick(
    *,
    title: Title | None,
    display_name: DisplayName,
    name: PlayerName | None,
) -> str:
    """Собрать «полный ник» по правилу ГДД §2.1 (legacy / RU-only).

    Формат `[Титул] [Название] [Имя]` с пропуском `None`-частей.
    Новичок без титула и имени → только название.

    Используется `bot/presenters/forest.py` (1.5.D мигрирует его на
    презентер с `IMessageBundle`); `ProfilePresenter` и `TopPresenter`
    используют `_render_full_nick(...)` с локализацией титула через
    bundle.
    """
    return _render_full_nick(
        title_str=_TITLE_RU[title] if title is not None else None,
        display_name=display_name,
        name=name,
    )


def _render_full_nick(
    *,
    title_str: str | None,
    display_name: DisplayName,
    name: PlayerName | None,
) -> str:
    """Внутренний join «Титул Название Имя» по уже-локализованной строке титула."""
    parts: list[str] = []
    if title_str is not None:
        parts.append(title_str)
    parts.append(display_name.value)
    if name is not None:
        parts.append(name.value)
    return " ".join(parts)


def title_message_key(title: Title) -> MessageKey:
    """Ключ `IMessageBundle` для локализованного имени титула.

    Привязка: `Title.NEWBIE = "newbie"` → `profile-title-newbie`.
    Если в `domain.player.value_objects.Title` появится новый член,
    но соответствующий ключ забудут добавить в `.ftl` — `IMessageBundle`
    бросит `MessageKeyError`, и тест `test_only_known_titles_supported`
    в `tests/unit/bot/presenters/test_profile.py` упадёт.
    """
    return MessageKey(f"profile-title-{title.value}")


class ProfilePresenter:
    """Локализованный рендер ответов `/profile` через `IMessageBundle`."""

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def group(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GROUP, locale=locale)

    def other(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_OTHER, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    def card(self, view: ProfileView, *, locale: Locale) -> str:
        """Полная карточка `/profile` (ГДД §2.2).

        `ProfileView` уже содержит `Player` (из БД) и заранее посчитанный
        `DisplayName` — презентер только склеивает строки и спрашивает у
        bundle локализованное имя титула.

        Equipment skipped до Спринта 1.3+ (см. модульный docstring).
        """
        title_str: str | None = None
        if view.player.title is not None:
            title_str = self._bundle.format(
                title_message_key(view.player.title),
                locale=locale,
            )
        nick = _render_full_nick(
            title_str=title_str,
            display_name=view.display_name,
            name=view.player.name,
        )
        return self._bundle.format(
            _KEY_CARD,
            locale=locale,
            nick=nick,
            length_cm=view.player.length.cm,
            thickness_level=view.player.thickness.level,
        )


__all__ = [
    "ProfilePresenter",
    "render_full_nick",
    "title_message_key",
]
