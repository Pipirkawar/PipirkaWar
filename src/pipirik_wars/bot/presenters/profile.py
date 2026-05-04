"""Презентер карточки персонажа `/profile` (Спринт 1.1.9, ГДД §2.1/§2.2).

Тонкий слой между use-case-ом `GetProfile` и Telegram-handler-ом.
Не делает I/O, не зависит от инфраструктуры — берёт `ProfileView`
(содержит `Player` + рассчитанный `DisplayName`) и возвращает строку,
готовую к отправке через `message.answer(...)`.

Из ГДД §2.1 формат «полного ника» — `[Титул] [Название] [Имя]`,
*пропуская* отсутствующие части (новичок без титула и без имени
показывается как `Пипирик`).

Карточка из ГДД §2.2:

    🏷 Ядрёный Бананчик Коляндр

    📏Длина: 47 см
    📐Толщина: 5

    🎽Экипировка:
       🎩Шлем Берсерка [эпический]
       …

В Спринте 1.1.E экипировки **ещё нет** — она появится в Спринте 1.3+
(дроп предметов из леса). Пока строка «Экипировка» либо опускается,
либо рендерится как «🎽 Экипировка: пока пусто», чтобы карточка не
вводила игрока в заблуждение и не выглядела «недозагруженной».
"""

from __future__ import annotations

from pipirik_wars.application.player import ProfileView
from pipirik_wars.domain.player import DisplayName, PlayerName, Title

# ГДД §2.4: сейчас определён только один титул `Title.NEWBIE`.
# Локализованные имена живут здесь, чтобы handler-у не нужно было
# знать про доменный enum — он просто получает готовую строку.
# При расширении таблицы титулов (Q12b/Q13 в `current_tasks.md`)
# добавляются новые ключи; маппинг проверяется тестами.
_TITLE_RU: dict[Title, str] = {
    Title.NEWBIE: "Новичок",
}


def render_full_nick(
    *,
    title: Title | None,
    display_name: DisplayName,
    name: PlayerName | None,
) -> str:
    """Собрать «полный ник» по правилу ГДД §2.1.

    Формат `[Титул] [Название] [Имя]` с пропуском `None`-частей.
    Новичок без титула и имени → только название.

    Примеры:

    - `Title=None, name=None`  → ``"Пипирик"``
    - `Title=NEWBIE, name=None` → ``"Новичок Пипирик"``
    - `Title=NEWBIE, name=PlayerName("Иванушка")` → ``"Новичок Пипирик Иванушка"``
    """
    parts: list[str] = []
    if title is not None:
        parts.append(_localized_title(title))
    parts.append(display_name.value)
    if name is not None:
        parts.append(name.value)
    return " ".join(parts)


def _localized_title(title: Title) -> str:
    """Маппинг доменного enum → русская строка для UI.

    `KeyError` означало бы, что мы добавили в `domain.player.value_objects.Title`
    новое значение и забыли локализовать его здесь. Это поведение by-design:
    тест `test_render_profile_card.py` ловит расхождение и падает.
    """
    return _TITLE_RU[title]


def render_profile_card(view: ProfileView) -> str:
    """Полная карточка `/profile` (ГДД §2.2).

    `ProfileView` уже содержит `Player` (из БД) и заранее посчитанный
    `DisplayName` — презентер только склеивает строки.

    Equipment skipped до Спринта 1.3+ (см. модульный docstring).
    """
    player = view.player
    nick = render_full_nick(
        title=player.title,
        display_name=view.display_name,
        name=player.name,
    )
    return (
        f"🏷 {nick}\n"
        "\n"
        f"📏 Длина: {player.length.cm} см\n"
        f"📐 Толщина: {player.thickness.level}\n"
        "\n"
        "🎽 Экипировка: пока пусто"
    )
