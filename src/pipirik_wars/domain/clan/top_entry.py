"""DTO `ClanTopEntry` для команды `/clantop` (Спринт 2.2, ПД 2.2.1).

Иммутабельный snapshot одной строки топа кланов: внутренний `clan_id`,
название клана из Telegram-чата, сумма длин активных участников
и количество этих участников. Позиция в рейтинге (`rank`) определяется
индексом в возвращаемой последовательности — её рендерит презентер.

Лежит в `domain/`, а не в `application/`, потому что репозитории
(`IClanRepository`) тоже доменный слой и им нужен этот VO как
return-тип. `application/top/` использует тот же VO как DTO без
дублирования.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.clan.value_objects import ClanTitle


@dataclass(frozen=True, slots=True)
class ClanTopEntry:
    """Один ряд топа кланов: «Название — сумма длин (число участников)».

    `total_length_cm` — сумма `length_cm` всех `ACTIVE`-игроков,
    состоящих в `ACTIVE`-клане. Frozen-кланы и не-active-игроки
    исключаются на уровне SQL-агрегации (см. реализацию
    `SqlAlchemyClanRepository.list_top_by_total_length`).
    """

    clan_id: int
    clan_title: ClanTitle
    total_length_cm: int
    member_count: int

    def __post_init__(self) -> None:
        if self.total_length_cm < 0:
            raise ValueError(
                f"total_length_cm must be >= 0, got {self.total_length_cm}",
            )
        if self.member_count < 0:
            raise ValueError(
                f"member_count must be >= 0, got {self.member_count}",
            )
        if self.clan_id <= 0:
            raise ValueError(f"clan_id must be > 0, got {self.clan_id}")
