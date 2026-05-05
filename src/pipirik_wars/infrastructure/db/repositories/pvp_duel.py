"""Реализация `IDuelRepository` поверх таблиц `pvp_duels` + `pvp_duel_rounds`.

Сериализация агрегата `Duel`:

* root-row → `pvp_duels` (один в один по полям; enum-ы сохраняются как
  строки `value`-ов; `pending_round` разворачивается в 4 nullable-
  колонки `pending_pX_attack`/`pending_pX_block`; `final_outcome` —
  в 5 nullable-колонок `final_*`);
* `completed_rounds: tuple[RoundOutcome, ...]` → 1:N в `pvp_duel_rounds`
  по `(duel_id, round_num)`. На `save(...)` новые раунды добавляются,
  старые остаются нетронутыми (round-record иммутабелен после
  авторазрешения — в домене нет API для редактирования прошлых раундов).

Все БД-уровневые `IntegrityError`-ы (нарушение CHECK-/FK-инвариантов)
конвертируются в доменный `IntegrityError` из `pipirik_wars.shared.errors`
и не утекают наружу.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError

from pipirik_wars.domain.pvp.duel import Duel, DuelMode, DuelState, PendingRound
from pipirik_wars.domain.pvp.entities import (
    DuelOutcome,
    DuelWinner,
    Position,
    RoundChoice,
    RoundOutcome,
)
from pipirik_wars.domain.pvp.repositories import IDuelRepository
from pipirik_wars.infrastructure.db.models import PvpDuelORM, PvpDuelRoundORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError


def _round_choice_to_columns(choice: RoundChoice) -> tuple[str, str]:
    return (choice.attack.value, choice.block.value)


def _columns_to_round_choice(*, attack: str, block: str) -> RoundChoice:
    return RoundChoice(attack=Position(attack), block=Position(block))


def _row_to_round_outcome(row: PvpDuelRoundORM) -> RoundOutcome:
    return RoundOutcome(
        p1_choice=_columns_to_round_choice(attack=row.p1_attack, block=row.p1_block),
        p2_choice=_columns_to_round_choice(attack=row.p2_attack, block=row.p2_block),
        p1_attack_blocked=row.p1_attack_blocked,
        p2_attack_blocked=row.p2_attack_blocked,
        p1_damage_to_p2=row.p1_damage_to_p2,
        p2_damage_to_p1=row.p2_damage_to_p1,
    )


def _round_outcome_to_row(
    *, duel_id: int, round_num: int, outcome: RoundOutcome
) -> PvpDuelRoundORM:
    p1_attack, p1_block = _round_choice_to_columns(outcome.p1_choice)
    p2_attack, p2_block = _round_choice_to_columns(outcome.p2_choice)
    return PvpDuelRoundORM(
        duel_id=duel_id,
        round_num=round_num,
        p1_attack=p1_attack,
        p1_block=p1_block,
        p2_attack=p2_attack,
        p2_block=p2_block,
        p1_attack_blocked=outcome.p1_attack_blocked,
        p2_attack_blocked=outcome.p2_attack_blocked,
        p1_damage_to_p2=outcome.p1_damage_to_p2,
        p2_damage_to_p1=outcome.p2_damage_to_p1,
    )


def _row_to_duel(*, row: PvpDuelORM, round_rows: list[PvpDuelRoundORM]) -> Duel:
    completed_rounds = tuple(
        _row_to_round_outcome(r) for r in sorted(round_rows, key=lambda r: r.round_num)
    )
    pending_round: PendingRound | None = None
    if row.pending_round_num is not None:
        p1_choice: RoundChoice | None = None
        if row.pending_p1_attack is not None and row.pending_p1_block is not None:
            p1_choice = _columns_to_round_choice(
                attack=row.pending_p1_attack,
                block=row.pending_p1_block,
            )
        p2_choice: RoundChoice | None = None
        if row.pending_p2_attack is not None and row.pending_p2_block is not None:
            p2_choice = _columns_to_round_choice(
                attack=row.pending_p2_attack,
                block=row.pending_p2_block,
            )
        pending_round = PendingRound(
            round_num=row.pending_round_num,
            p1_choice=p1_choice,
            p2_choice=p2_choice,
        )

    final_outcome: DuelOutcome | None = None
    if row.final_winner is not None:
        # Все final_* колонки заполняются вместе (CHECK ck_pvp_duels_state_invariants).
        assert row.final_p1_total_dealt is not None
        assert row.final_p2_total_dealt is not None
        assert row.final_p1_delta_cm is not None
        assert row.final_p2_delta_cm is not None
        final_outcome = DuelOutcome(
            rounds=completed_rounds,
            p1_total_dealt=row.final_p1_total_dealt,
            p2_total_dealt=row.final_p2_total_dealt,
            p1_delta_cm=row.final_p1_delta_cm,
            p2_delta_cm=row.final_p2_delta_cm,
            winner=DuelWinner(row.final_winner),
        )

    return Duel(
        id=row.id,
        challenger_id=row.challenger_id,
        challenged_id=row.challenged_id,
        mode=DuelMode(row.mode),
        state=DuelState(row.state),
        hit_pct=row.hit_pct,
        expected_rounds=row.expected_rounds,
        created_at=ensure_utc(row.created_at),
        accepted_at=ensure_utc(row.accepted_at) if row.accepted_at is not None else None,
        completed_at=ensure_utc(row.completed_at) if row.completed_at is not None else None,
        cancelled_at=ensure_utc(row.cancelled_at) if row.cancelled_at is not None else None,
        p1_initial_length_cm=row.p1_initial_length_cm,
        p2_initial_length_cm=row.p2_initial_length_cm,
        completed_rounds=completed_rounds,
        pending_round=pending_round,
        final_outcome=final_outcome,
    )


def _apply_duel_to_row(*, row: PvpDuelORM, duel: Duel) -> None:
    """Записать поля агрегата в ORM-row (используется в add и save)."""
    row.challenger_id = duel.challenger_id
    row.challenged_id = duel.challenged_id
    row.mode = duel.mode.value
    row.state = duel.state.value
    row.hit_pct = duel.hit_pct
    row.expected_rounds = duel.expected_rounds
    row.p1_initial_length_cm = duel.p1_initial_length_cm
    row.p2_initial_length_cm = duel.p2_initial_length_cm
    row.created_at = duel.created_at
    row.accepted_at = duel.accepted_at
    row.completed_at = duel.completed_at
    row.cancelled_at = duel.cancelled_at

    if duel.pending_round is None:
        row.pending_round_num = None
        row.pending_p1_attack = None
        row.pending_p1_block = None
        row.pending_p2_attack = None
        row.pending_p2_block = None
    else:
        row.pending_round_num = duel.pending_round.round_num
        if duel.pending_round.p1_choice is None:
            row.pending_p1_attack = None
            row.pending_p1_block = None
        else:
            attack, block = _round_choice_to_columns(duel.pending_round.p1_choice)
            row.pending_p1_attack = attack
            row.pending_p1_block = block
        if duel.pending_round.p2_choice is None:
            row.pending_p2_attack = None
            row.pending_p2_block = None
        else:
            attack, block = _round_choice_to_columns(duel.pending_round.p2_choice)
            row.pending_p2_attack = attack
            row.pending_p2_block = block

    if duel.final_outcome is None:
        row.final_p1_total_dealt = None
        row.final_p2_total_dealt = None
        row.final_p1_delta_cm = None
        row.final_p2_delta_cm = None
        row.final_winner = None
    else:
        row.final_p1_total_dealt = duel.final_outcome.p1_total_dealt
        row.final_p2_total_dealt = duel.final_outcome.p2_total_dealt
        row.final_p1_delta_cm = duel.final_outcome.p1_delta_cm
        row.final_p2_delta_cm = duel.final_outcome.p2_delta_cm
        row.final_winner = duel.final_outcome.winner.value


class SqlAlchemyDuelRepository(IDuelRepository):
    """Реализация `IDuelRepository` поверх SQLAlchemy 2.x async session.

    Read-after-write: `add(...)` возвращает агрегат с проставленным `id`
    (через `flush`-уплыв в БД и чтение autoincrement-PK), `save(...)` —
    с зеркальным состоянием row-а после flush-а.
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def add(self, duel: Duel) -> Duel:
        if duel.id is not None:
            raise DomainIntegrityError(
                f"Duel with pre-set id={duel.id} cannot be added; use save()",
            )
        row = PvpDuelORM(
            challenger_id=duel.challenger_id,
            challenged_id=duel.challenged_id,
            mode=duel.mode.value,
            state=duel.state.value,
            hit_pct=duel.hit_pct,
            expected_rounds=duel.expected_rounds,
            p1_initial_length_cm=duel.p1_initial_length_cm,
            p2_initial_length_cm=duel.p2_initial_length_cm,
            created_at=duel.created_at,
            accepted_at=duel.accepted_at,
            completed_at=duel.completed_at,
            cancelled_at=duel.cancelled_at,
        )
        _apply_duel_to_row(row=row, duel=duel)
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to add pvp_duel for challenger_id={duel.challenger_id}: {exc.orig}",
            ) from exc

        for idx, outcome in enumerate(duel.completed_rounds, start=1):
            self._uow.session.add(
                _round_outcome_to_row(duel_id=row.id, round_num=idx, outcome=outcome),
            )
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to persist pvp_duel_rounds for duel_id={row.id}: {exc.orig}",
            ) from exc

        round_rows = await self._load_round_rows(duel_id=row.id)
        return _row_to_duel(row=row, round_rows=round_rows)

    async def get_by_id(self, *, duel_id: int) -> Duel | None:
        row = await self._uow.session.get(PvpDuelORM, duel_id)
        if row is None:
            return None
        round_rows = await self._load_round_rows(duel_id=duel_id)
        return _row_to_duel(row=row, round_rows=round_rows)

    async def save(self, duel: Duel) -> Duel:
        if duel.id is None:
            raise DomainIntegrityError("Duel.save requires id; use add() for new duels")
        row = await self._uow.session.get(PvpDuelORM, duel.id)
        if row is None:
            raise DomainIntegrityError(f"Duel id={duel.id} not found")
        _apply_duel_to_row(row=row, duel=duel)

        existing_round_nums = {r.round_num for r in await self._load_round_rows(duel_id=duel.id)}
        for idx, outcome in enumerate(duel.completed_rounds, start=1):
            if idx in existing_round_nums:
                continue
            self._uow.session.add(
                _round_outcome_to_row(duel_id=duel.id, round_num=idx, outcome=outcome),
            )
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to save pvp_duel id={duel.id}: {exc.orig}",
            ) from exc

        round_rows = await self._load_round_rows(duel_id=duel.id)
        return _row_to_duel(row=row, round_rows=round_rows)

    async def _load_round_rows(self, *, duel_id: int) -> list[PvpDuelRoundORM]:
        result = await self._uow.session.execute(
            select(PvpDuelRoundORM)
            .where(PvpDuelRoundORM.duel_id == duel_id)
            .order_by(PvpDuelRoundORM.round_num.asc()),
        )
        return list(result.scalars().all())
