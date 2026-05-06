"""DTO `ClanMassDuelHistoryEntry` для команды `/clan_history` (Спринт 2.2.G, ПД 2.2.5).

Иммутабельный snapshot одной строки журнала клановых атак: внутренний
`duel_id`, противник, исход с точки зрения нашего клана, итоговые
суммы урона и timestamp-ы. Лежит в `domain/pvp/`, потому что
репозиторий (`IMassDuelRepository`) — доменный слой и ему нужен этот
VO как return-тип read-side query (`IClanMassDuelHistoryQuery`).
`application/pvp/` использует тот же VO как DTO без дублирования.

Семантика «нашей стороны» — точка зрения **запрашивающего** клана:
если клан был `clan1` в бою — `our_total_dealt = clan1_total_dealt`,
`our_delta_cm = clan1_delta_cm`; если был `clan2` — наоборот. Это
позволяет показать пользователю «сколько мы нанесли / сколько
получили / победа|поражение|ничья» без дополнительной логики на
стороне презентера.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pipirik_wars.domain.clan.value_objects import ClanTitle
from pipirik_wars.domain.pvp.mass import MassDuelWinner
from pipirik_wars.domain.pvp.mass_duel import MassDuelState


class ClanMassDuelOutcomeForUs(StrEnum):
    """Исход массового PvP-боя с точки зрения запрашивающего клана.

    Симметрично `MassDuelWinner`, но в системе координат «мы / они»:
    `VICTORY` если наш клан выиграл, `DEFEAT` если проиграл,
    `DRAW` если ничья, `CANCELLED` если бой был отменён (нет
    финального outcome-а).
    """

    VICTORY = "victory"
    DEFEAT = "defeat"
    DRAW = "draw"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ClanMassDuelHistoryEntry:
    """Один ряд журнала клановых атак: «противник, исход, дельты, время».

    `our_clan_id` — клан, чью историю мы рендерим (запросивший
    `/clan_history`); `opponent_clan_id` — другой участник этого
    конкретного боя. Маппинг clan1/clan2 (storage) → us/them
    (presentation) — внутри `__post_init__`: проверяем, что
    `our_clan_id` встречается ровно раз в (`clan1_id`, `clan2_id`),
    но сам маппинг делает уже SQL-проекция (см. реализацию
    `SqlAlchemyClanMassDuelHistoryQuery`).

    Контракт инвариантов:
    - `duel_id > 0`, `our_clan_id > 0`, `opponent_clan_id > 0`,
      `our_clan_id != opponent_clan_id`;
    - `our_total_dealt >= 0`, `our_total_received >= 0`;
    - `our_delta_cm + opponent_delta_cm == 0` (zero-sum, как и в
      `MassDuelOutcome` 2.2.B);
    - `our_participants_count >= 1`, `opponent_participants_count >= 1`;
    - `outcome == CANCELLED` ⇔ `state == CANCELLED` ⇔ `completed_at is None`;
    - `outcome == VICTORY` ⇒ `our_total_dealt > our_total_received`,
      `outcome == DEFEAT` ⇒ `our_total_dealt < our_total_received`,
      `outcome == DRAW` ⇒ `our_total_dealt == our_total_received`.
    """

    duel_id: int
    our_clan_id: int
    opponent_clan_id: int
    opponent_clan_title: ClanTitle
    state: MassDuelState
    outcome: ClanMassDuelOutcomeForUs
    our_total_dealt: int
    our_total_received: int
    our_delta_cm: int
    opponent_delta_cm: int
    our_participants_count: int
    opponent_participants_count: int
    created_at: datetime
    completed_at: datetime | None

    def __post_init__(self) -> None:  # noqa: PLR0912 — линейная цепочка инвариантов VO
        if self.duel_id <= 0:
            raise ValueError(f"duel_id must be > 0, got {self.duel_id}")
        if self.our_clan_id <= 0:
            raise ValueError(f"our_clan_id must be > 0, got {self.our_clan_id}")
        if self.opponent_clan_id <= 0:
            raise ValueError(f"opponent_clan_id must be > 0, got {self.opponent_clan_id}")
        if self.our_clan_id == self.opponent_clan_id:
            raise ValueError(
                f"our_clan_id and opponent_clan_id must differ, got {self.our_clan_id}",
            )
        if self.our_total_dealt < 0:
            raise ValueError(
                f"our_total_dealt must be >= 0, got {self.our_total_dealt}",
            )
        if self.our_total_received < 0:
            raise ValueError(
                f"our_total_received must be >= 0, got {self.our_total_received}",
            )
        if self.our_delta_cm + self.opponent_delta_cm != 0:
            raise ValueError(
                "our_delta_cm + opponent_delta_cm must equal 0 (zero-sum), "
                f"got our={self.our_delta_cm}, opponent={self.opponent_delta_cm}",
            )
        if self.our_participants_count <= 0:
            raise ValueError(
                f"our_participants_count must be > 0, got {self.our_participants_count}",
            )
        if self.opponent_participants_count <= 0:
            raise ValueError(
                f"opponent_participants_count must be > 0, got {self.opponent_participants_count}",
            )
        is_cancelled_state = self.state is MassDuelState.CANCELLED
        is_cancelled_outcome = self.outcome is ClanMassDuelOutcomeForUs.CANCELLED
        if is_cancelled_state != is_cancelled_outcome:
            raise ValueError(
                f"state={self.state.value} and outcome={self.outcome.value} "
                "must agree (both CANCELLED or both not)",
            )
        if is_cancelled_state and self.completed_at is not None:
            raise ValueError(
                f"completed_at must be None for CANCELLED entries, got {self.completed_at}",
            )
        if not is_cancelled_state and self.completed_at is None:
            raise ValueError(
                f"completed_at must be set for state={self.state.value}",
            )
        if (
            self.outcome is ClanMassDuelOutcomeForUs.VICTORY
            and self.our_total_dealt <= self.our_total_received
        ):
            raise ValueError(
                "VICTORY requires our_total_dealt > our_total_received, "
                f"got dealt={self.our_total_dealt}, received={self.our_total_received}",
            )
        if (
            self.outcome is ClanMassDuelOutcomeForUs.DEFEAT
            and self.our_total_dealt >= self.our_total_received
        ):
            raise ValueError(
                "DEFEAT requires our_total_dealt < our_total_received, "
                f"got dealt={self.our_total_dealt}, received={self.our_total_received}",
            )
        if (
            self.outcome is ClanMassDuelOutcomeForUs.DRAW
            and self.our_total_dealt != self.our_total_received
        ):
            raise ValueError(
                "DRAW requires our_total_dealt == our_total_received, "
                f"got dealt={self.our_total_dealt}, received={self.our_total_received}",
            )

    @staticmethod
    def outcome_from_winner(
        *,
        winner: MassDuelWinner,
        our_side: str,
    ) -> ClanMassDuelOutcomeForUs:
        """Маппинг (`MassDuelWinner`, our side) → `ClanMassDuelOutcomeForUs`.

        `our_side` — строковый литерал `"clan1"` / `"clan2"` (как
        в БД-колонке `clan_side` `pvp_mass_duel_choices`). Любое
        другое значение — `ValueError`.
        """
        if our_side not in ("clan1", "clan2"):
            raise ValueError(f"our_side must be 'clan1' or 'clan2', got {our_side!r}")
        if winner is MassDuelWinner.DRAW:
            return ClanMassDuelOutcomeForUs.DRAW
        if winner is MassDuelWinner.CLAN1:
            return (
                ClanMassDuelOutcomeForUs.VICTORY
                if our_side == "clan1"
                else ClanMassDuelOutcomeForUs.DEFEAT
            )
        return (
            ClanMassDuelOutcomeForUs.VICTORY
            if our_side == "clan2"
            else ClanMassDuelOutcomeForUs.DEFEAT
        )


__all__ = [
    "ClanMassDuelHistoryEntry",
    "ClanMassDuelOutcomeForUs",
]
