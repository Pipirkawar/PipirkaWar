"""DTO для записи топа игроков (Спринт 1.4.C / ПД 1.4.6).

`TopPlayerEntry` — иммутабельный snapshot одного ряда `/top`.
Содержит уже посчитанный `DisplayName` (формат «Хвостик/Палочка/...»),
чтобы handler не лез в `IBalanceConfig` на каждый ряд. Позиция в
рейтинге (`rank`) определяется индексом в возвращаемой
последовательности — её рендерит презентер.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.player import DisplayName, PlayerName, Title


@dataclass(frozen=True, slots=True)
class TopPlayerEntry:
    """Один ряд топа: «Титул Название Имя — N см»."""

    title: Title | None
    display_name: DisplayName
    name: PlayerName | None
    length_cm: int

    def __post_init__(self) -> None:
        if self.length_cm < 0:
            raise ValueError(f"length_cm must be >= 0, got {self.length_cm}")
