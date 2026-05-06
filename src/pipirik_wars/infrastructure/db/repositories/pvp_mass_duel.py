"""Реализация `IMassDuelRepository` поверх таблиц `pvp_mass_duels` +
`pvp_mass_duel_choices` + `pvp_mass_duel_damage_entries` (Спринт 2.2.D).

Сериализация агрегата :class:`MassDuel` (домен 2.2.C):

* root-row → `pvp_mass_duels` — `clan{1,2}_id`, `state`, `hit_pct`,
  `created_at` / `completed_at` / `cancelled_at`, финальные дельты
  и `final_winner` (nullable, заполняются только при `COMPLETED`);
* параллельные кортежи `clan{1,2}_member_ids` × `clan{1,2}_initial_lengths`
  × `clan{1,2}_choices` → `pvp_mass_duel_choices` (1:N от root-а):
  одна строка на каждого участника, поля `attack`/`block`/`submitted_at`
  nullable до `submit_move`-а;
* `final_outcome.outcome.damage_entries` → `pvp_mass_duel_damage_entries`
  (1:N от root-а, только для COMPLETED-боёв): один row на каждый
  разрешённый удар, порядок сохраняется через 0-based `entry_idx`.

Все БД-уровневые `IntegrityError`-ы (нарушение CHECK-/FK-инвариантов)
конвертируются в доменный `IntegrityError` из `pipirik_wars.shared.errors`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError

from pipirik_wars.domain.pvp.entities import Position
from pipirik_wars.domain.pvp.mass import (
    MassDamageEntry,
    MassDuelOutcome,
    MassDuelWinner,
    MassRoundChoice,
    MassRoundOutcome,
)
from pipirik_wars.domain.pvp.mass_duel import MassDuel, MassDuelState
from pipirik_wars.domain.pvp.repositories import IMassDuelRepository
from pipirik_wars.infrastructure.db.models import (
    PvpMassDuelChoiceORM,
    PvpMassDuelDamageEntryORM,
    PvpMassDuelORM,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError

_CLAN1_SIDE = "clan1"
_CLAN2_SIDE = "clan2"


def _choice_orm_to_value_object(row: PvpMassDuelChoiceORM) -> MassRoundChoice | None:
    if row.attack is None or row.block is None:
        return None
    return MassRoundChoice(
        player_id=row.player_id,
        attack=Position(row.attack),
        block=Position(row.block),
    )


def _damage_entry_orm_to_value_object(row: PvpMassDuelDamageEntryORM) -> MassDamageEntry:
    return MassDamageEntry(
        attacker_id=row.attacker_id,
        defender_id=row.defender_id,
        attacker_attack=Position(row.attacker_attack),
        defender_block=Position(row.defender_block),
        blocked=row.blocked,
        damage_cm=row.damage_cm,
    )


def _build_clan_side(
    *,
    duel_id: int,
    member_ids: tuple[int, ...],
    initial_lengths: tuple[int, ...],
    choices: tuple[MassRoundChoice | None, ...],
    side: str,
    submitted_at: datetime | None,
) -> list[PvpMassDuelChoiceORM]:
    """Сконструировать ORM-row-ы для одной стороны массового боя.

    `submitted_at` подсовывается уже-отправленным выборам. Для случая
    `add(...)` (всё ещё `IN_PROGRESS` без submit-ов) выборы будут
    `None` и `submitted_at` останется тоже `None` независимо от
    переданного значения.
    """
    rows: list[PvpMassDuelChoiceORM] = []
    for player_id, length, choice in zip(member_ids, initial_lengths, choices, strict=True):
        attack = choice.attack.value if choice is not None else None
        block = choice.block.value if choice is not None else None
        rows.append(
            PvpMassDuelChoiceORM(
                duel_id=duel_id,
                player_id=player_id,
                clan_side=side,
                initial_length_cm=length,
                attack=attack,
                block=block,
                submitted_at=submitted_at if choice is not None else None,
            )
        )
    return rows


def _split_choice_rows_by_side(
    rows: list[PvpMassDuelChoiceORM],
) -> tuple[list[PvpMassDuelChoiceORM], list[PvpMassDuelChoiceORM]]:
    clan1 = sorted(
        (r for r in rows if r.clan_side == _CLAN1_SIDE),
        key=lambda r: r.player_id,
    )
    clan2 = sorted(
        (r for r in rows if r.clan_side == _CLAN2_SIDE),
        key=lambda r: r.player_id,
    )
    return clan1, clan2


def _row_to_mass_duel(
    *,
    row: PvpMassDuelORM,
    choice_rows: list[PvpMassDuelChoiceORM],
    damage_rows: list[PvpMassDuelDamageEntryORM],
) -> MassDuel:
    clan1_rows, clan2_rows = _split_choice_rows_by_side(choice_rows)

    clan1_member_ids = tuple(r.player_id for r in clan1_rows)
    clan2_member_ids = tuple(r.player_id for r in clan2_rows)
    clan1_initial_lengths = tuple(r.initial_length_cm for r in clan1_rows)
    clan2_initial_lengths = tuple(r.initial_length_cm for r in clan2_rows)
    clan1_choices = tuple(_choice_orm_to_value_object(r) for r in clan1_rows)
    clan2_choices = tuple(_choice_orm_to_value_object(r) for r in clan2_rows)

    final_outcome: MassDuelOutcome | None = None
    if row.final_winner is not None:
        # CHECK ck_pvp_mass_duels_state_invariants гарантирует, что при
        # COMPLETED все final_* заполнены — assert-ы помогают mypy.
        assert row.final_clan1_total_dealt is not None
        assert row.final_clan2_total_dealt is not None
        assert row.final_clan1_delta_cm is not None
        assert row.final_clan2_delta_cm is not None
        damage_entries = tuple(
            _damage_entry_orm_to_value_object(r)
            for r in sorted(damage_rows, key=lambda d: d.entry_idx)
        )
        final_outcome = MassDuelOutcome(
            outcome=MassRoundOutcome(
                damage_entries=damage_entries,
                clan1_total_dealt=row.final_clan1_total_dealt,
                clan2_total_dealt=row.final_clan2_total_dealt,
            ),
            clan1_total_dealt=row.final_clan1_total_dealt,
            clan2_total_dealt=row.final_clan2_total_dealt,
            clan1_delta_cm=row.final_clan1_delta_cm,
            clan2_delta_cm=row.final_clan2_delta_cm,
            winner=MassDuelWinner(row.final_winner),
        )

    return MassDuel(
        id=row.id,
        clan1_id=row.clan1_id,
        clan2_id=row.clan2_id,
        state=MassDuelState(row.state),
        hit_pct=row.hit_pct,
        clan1_member_ids=clan1_member_ids,
        clan2_member_ids=clan2_member_ids,
        clan1_initial_lengths=clan1_initial_lengths,
        clan2_initial_lengths=clan2_initial_lengths,
        clan1_choices=clan1_choices,
        clan2_choices=clan2_choices,
        created_at=ensure_utc(row.created_at),
        completed_at=ensure_utc(row.completed_at) if row.completed_at is not None else None,
        cancelled_at=ensure_utc(row.cancelled_at) if row.cancelled_at is not None else None,
        final_outcome=final_outcome,
    )


def _apply_root_fields(*, row: PvpMassDuelORM, duel: MassDuel) -> None:
    """Записать поля root-row-а агрегата (без участников и damage-entries)."""
    row.clan1_id = duel.clan1_id
    row.clan2_id = duel.clan2_id
    row.state = duel.state.value
    row.hit_pct = duel.hit_pct
    row.created_at = duel.created_at
    row.completed_at = duel.completed_at
    row.cancelled_at = duel.cancelled_at

    if duel.final_outcome is None:
        row.final_clan1_total_dealt = None
        row.final_clan2_total_dealt = None
        row.final_clan1_delta_cm = None
        row.final_clan2_delta_cm = None
        row.final_winner = None
    else:
        row.final_clan1_total_dealt = duel.final_outcome.clan1_total_dealt
        row.final_clan2_total_dealt = duel.final_outcome.clan2_total_dealt
        row.final_clan1_delta_cm = duel.final_outcome.clan1_delta_cm
        row.final_clan2_delta_cm = duel.final_outcome.clan2_delta_cm
        row.final_winner = duel.final_outcome.winner.value


def _damage_entry_to_orm(
    *, duel_id: int, entry_idx: int, entry: MassDamageEntry
) -> PvpMassDuelDamageEntryORM:
    return PvpMassDuelDamageEntryORM(
        duel_id=duel_id,
        entry_idx=entry_idx,
        attacker_id=entry.attacker_id,
        defender_id=entry.defender_id,
        attacker_attack=entry.attacker_attack.value,
        defender_block=entry.defender_block.value,
        blocked=entry.blocked,
        damage_cm=entry.damage_cm,
    )


class SqlAlchemyMassDuelRepository(IMassDuelRepository):
    """Реализация `IMassDuelRepository` поверх SQLAlchemy 2.x async session.

    Read-after-write: `add(...)` возвращает агрегат с проставленным `id`
    (через `flush`-уплыв в БД и чтение autoincrement-PK), `save(...)` —
    с зеркальным состоянием row-а после flush-а.

    Mass-duel-ростер замораживается на момент `add(...)`: попытка
    `save(...)`-а с другим набором `clan{1,2}_member_ids` (например,
    после ручной правки в обход домена) возвращает ошибку
    `IntegrityError`. Само доменное API mutator-ов не меняет ростер,
    так что в нормальном flow это никогда не сработает.
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def add(self, duel: MassDuel) -> MassDuel:
        if duel.id is not None:
            raise DomainIntegrityError(
                f"MassDuel with pre-set id={duel.id} cannot be added; use save()",
            )

        row = PvpMassDuelORM(
            clan1_id=duel.clan1_id,
            clan2_id=duel.clan2_id,
            state=duel.state.value,
            hit_pct=duel.hit_pct,
            created_at=duel.created_at,
            completed_at=duel.completed_at,
            cancelled_at=duel.cancelled_at,
        )
        _apply_root_fields(row=row, duel=duel)
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to add pvp_mass_duel for clan1_id={duel.clan1_id},"
                f" clan2_id={duel.clan2_id}: {exc.orig}",
            ) from exc

        # На момент `add(...)` обычно state == IN_PROGRESS и все
        # выборы None; но домен теоретически допускает добавление
        # уже-частично-заполненного боя (например, при хот-патче после
        # рестарта), поэтому копируем submitted_at = created_at для
        # уже-отправленных выборов (точное значение не критично — оно
        # перезапишется на save()).
        for choice_row in _build_clan_side(
            duel_id=row.id,
            member_ids=duel.clan1_member_ids,
            initial_lengths=duel.clan1_initial_lengths,
            choices=duel.clan1_choices,
            side=_CLAN1_SIDE,
            submitted_at=duel.created_at,
        ):
            self._uow.session.add(choice_row)
        for choice_row in _build_clan_side(
            duel_id=row.id,
            member_ids=duel.clan2_member_ids,
            initial_lengths=duel.clan2_initial_lengths,
            choices=duel.clan2_choices,
            side=_CLAN2_SIDE,
            submitted_at=duel.created_at,
        ):
            self._uow.session.add(choice_row)

        if duel.final_outcome is not None:
            for entry_idx, entry in enumerate(duel.final_outcome.outcome.damage_entries):
                self._uow.session.add(
                    _damage_entry_to_orm(
                        duel_id=row.id,
                        entry_idx=entry_idx,
                        entry=entry,
                    ),
                )

        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to persist pvp_mass_duel rosters for duel_id={row.id}: {exc.orig}",
            ) from exc

        choice_rows = await self._load_choice_rows(duel_id=row.id)
        damage_rows = await self._load_damage_rows(duel_id=row.id)
        return _row_to_mass_duel(row=row, choice_rows=choice_rows, damage_rows=damage_rows)

    async def get_by_id(self, *, duel_id: int) -> MassDuel | None:
        row = await self._uow.session.get(PvpMassDuelORM, duel_id)
        if row is None:
            return None
        choice_rows = await self._load_choice_rows(duel_id=duel_id)
        damage_rows = await self._load_damage_rows(duel_id=duel_id)
        return _row_to_mass_duel(row=row, choice_rows=choice_rows, damage_rows=damage_rows)

    async def save(self, duel: MassDuel) -> MassDuel:
        if duel.id is None:
            raise DomainIntegrityError(
                "MassDuel.save requires id; use add() for new mass-duels",
            )
        row = await self._uow.session.get(PvpMassDuelORM, duel.id)
        if row is None:
            raise DomainIntegrityError(f"MassDuel id={duel.id} not found")
        _apply_root_fields(row=row, duel=duel)

        existing_choice_rows = await self._load_choice_rows(duel_id=duel.id)
        # Свериться, что ростер совпадает (инвариант frozen-roster).
        existing_clan1_ids = sorted(
            r.player_id for r in existing_choice_rows if r.clan_side == _CLAN1_SIDE
        )
        existing_clan2_ids = sorted(
            r.player_id for r in existing_choice_rows if r.clan_side == _CLAN2_SIDE
        )
        if (
            tuple(existing_clan1_ids) != duel.clan1_member_ids
            or tuple(existing_clan2_ids) != duel.clan2_member_ids
        ):
            raise DomainIntegrityError(
                f"MassDuel id={duel.id} roster mismatch: cannot change participants"
                " between add() and save()",
            )

        # Обновить выборы участников: каждый row сопоставляется
        # с актуальным choice. Submitted_at не сбрасываем, если уже
        # был; домен запрещает «отзывать» выбор обратно в None.
        existing_by_pid: dict[int, PvpMassDuelChoiceORM] = {
            r.player_id: r for r in existing_choice_rows
        }
        for member_ids, choices, _ in (
            (duel.clan1_member_ids, duel.clan1_choices, _CLAN1_SIDE),
            (duel.clan2_member_ids, duel.clan2_choices, _CLAN2_SIDE),
        ):
            for player_id, choice in zip(member_ids, choices, strict=True):
                existing_row = existing_by_pid[player_id]
                if choice is None:
                    # Домен не должен возвращать выбор из non-None в None;
                    # на всякий случай оставляем существующее значение.
                    continue
                # Устанавливаем submitted_at только если ранее не был.
                if existing_row.submitted_at is None:
                    existing_row.submitted_at = duel.completed_at or duel.created_at
                existing_row.attack = choice.attack.value
                existing_row.block = choice.block.value

        # Damage-entries: иммутабельны после resolve(...). На save()
        # дописываем недостающие (по entry_idx) и не трогаем
        # существующие.
        if duel.final_outcome is not None:
            existing_damage_rows = await self._load_damage_rows(duel_id=duel.id)
            existing_idxs = {r.entry_idx for r in existing_damage_rows}
            for entry_idx, entry in enumerate(duel.final_outcome.outcome.damage_entries):
                if entry_idx in existing_idxs:
                    continue
                self._uow.session.add(
                    _damage_entry_to_orm(
                        duel_id=duel.id,
                        entry_idx=entry_idx,
                        entry=entry,
                    ),
                )

        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to save pvp_mass_duel id={duel.id}: {exc.orig}",
            ) from exc

        choice_rows = await self._load_choice_rows(duel_id=duel.id)
        damage_rows = await self._load_damage_rows(duel_id=duel.id)
        return _row_to_mass_duel(row=row, choice_rows=choice_rows, damage_rows=damage_rows)

    async def _load_choice_rows(self, *, duel_id: int) -> list[PvpMassDuelChoiceORM]:
        result = await self._uow.session.execute(
            select(PvpMassDuelChoiceORM)
            .where(PvpMassDuelChoiceORM.duel_id == duel_id)
            .order_by(
                PvpMassDuelChoiceORM.clan_side.asc(),
                PvpMassDuelChoiceORM.player_id.asc(),
            ),
        )
        return list(result.scalars().all())

    async def _load_damage_rows(self, *, duel_id: int) -> list[PvpMassDuelDamageEntryORM]:
        result = await self._uow.session.execute(
            select(PvpMassDuelDamageEntryORM)
            .where(PvpMassDuelDamageEntryORM.duel_id == duel_id)
            .order_by(PvpMassDuelDamageEntryORM.entry_idx.asc()),
        )
        return list(result.scalars().all())
