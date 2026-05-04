"""Value-объекты домена «Клан» (Спринт 1.1, ГДД §1.4)."""

from __future__ import annotations

import enum
from dataclasses import dataclass

# Telegram-чат пишет 255-символьное `title` в `getChat`; мы храним до
# 255 в БД. На уровне VO ограничиваем тем же значением, плюс требуем,
# чтобы строка не была пустой/whitespace.
_CLAN_TITLE_MAX_LENGTH: int = 255


class ChatKind(str, enum.Enum):
    """Вид Telegram-чата, в который добавили бота (для `clans.chat_kind`).

    `GROUP` — обычная группа (`chat.type == "group"`).
    `SUPERGROUP` — супергруппа (`chat.type == "supergroup"`).

    Telegram умеет «промоутить» group → supergroup автоматически:
    `chat_id` при этом меняется (с `-100…` префиксом). Use-case
    `RegisterClan` обрабатывает миграцию (см. Спринт 1.1.4); здесь же
    мы просто фиксируем, какой именно тип чата зарегистрирован прямо
    сейчас.
    """

    GROUP = "group"
    SUPERGROUP = "supergroup"


class ClanStatus(str, enum.Enum):
    """Статус клана (ГДД §1.5 / Спринт 1.1.6).

    `ACTIVE` — клан живёт нормально.
    `FROZEN` — бот удалён из чата клана; данные не теряем, но
    клановые механики (Глава дня, караван, масс-PvP) пропускаем.
    Повторное добавление бота → `ACTIVE` (см. `Clan.unfreeze`).
    """

    ACTIVE = "active"
    FROZEN = "frozen"


@dataclass(frozen=True, slots=True)
class ClanTitle:
    """Название клана = title чата из Telegram.

    Может меняться без рестарта (админ группы переименовал чат). Мы
    обновляем VO через `Clan.with_title(...)` в обработчике
    `chat_title` событий.
    """

    value: str

    def __post_init__(self) -> None:
        stripped = self.value.strip()
        if not stripped:
            raise ValueError("ClanTitle must not be empty/whitespace")
        if len(stripped) != len(self.value):
            raise ValueError("ClanTitle must not have leading/trailing whitespace")
        if len(self.value) > _CLAN_TITLE_MAX_LENGTH:
            raise ValueError(
                f"ClanTitle length must be <= {_CLAN_TITLE_MAX_LENGTH}, got {len(self.value)}"
            )
