"""Integration-тесты `SqlAlchemyDuelRepository` (Спринт 2.1.C).

Покрывают полный жизненный цикл агрегата `Duel` через persistence:

* PENDING_ACCEPT → save/load → cancel → save/load (CANCELLED);
* PENDING_ACCEPT → accept → save/load (IN_PROGRESS, lengths captured);
* IN_PROGRESS → submit_move (один игрок, pending_round частично заполнен);
* IN_PROGRESS → 3 раунда submit_move-ов → COMPLETED (final_outcome,
  completed_rounds в pvp_duel_rounds);
* GLOBAL_ONLY-вызов: challenged_id is None → accept устанавливает
  challenged_id;
* save() новых completed-раундов не дублирует существующие.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.player import Player
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelState,
    DuelWinner,
    Position,
    RoundChoice,
)
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyDuelRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError

NOW = datetime(2026, 5, 5, 10, 0, tzinfo=UTC)


def _ch(attack: Position, block: Position) -> RoundChoice:
    return RoundChoice(attack=attack, block=block)


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


def _build_chat_challenge(*, challenger_id: int, challenged_id: int) -> Duel:
    return Duel.create_challenge(
        challenger_id=challenger_id,
        challenged_id=challenged_id,
        mode=DuelMode.CHAT_THEN_GLOBAL,
        hit_pct=10,
        expected_rounds=3,
        now=NOW,
    )


def _build_global_challenge(*, challenger_id: int) -> Duel:
    return Duel.create_challenge(
        challenger_id=challenger_id,
        challenged_id=None,
        mode=DuelMode.GLOBAL_ONLY,
        hit_pct=10,
        expected_rounds=3,
        now=NOW,
    )


class TestPendingAcceptPersistence:
    @pytest.mark.asyncio
    async def test_add_chat_challenge_assigns_id(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        challenger = await _seed_player(uow, tg_id=1)
        challenged = await _seed_player(uow, tg_id=2)
        assert challenger.id is not None
        assert challenged.id is not None
        repo = SqlAlchemyDuelRepository(uow=uow)

        challenge = _build_chat_challenge(
            challenger_id=challenger.id,
            challenged_id=challenged.id,
        )
        async with uow:
            stored = await repo.add(challenge)

        assert stored.id is not None
        assert stored.state is DuelState.PENDING_ACCEPT
        assert stored.mode is DuelMode.CHAT_THEN_GLOBAL
        assert stored.challenger_id == challenger.id
        assert stored.challenged_id == challenged.id
        assert stored.hit_pct == 10
        assert stored.expected_rounds == 3
        assert stored.created_at == NOW
        assert stored.accepted_at is None
        assert stored.completed_at is None
        assert stored.cancelled_at is None
        assert stored.p1_initial_length_cm is None
        assert stored.p2_initial_length_cm is None
        assert stored.completed_rounds == ()
        assert stored.pending_round is None
        assert stored.final_outcome is None

    @pytest.mark.asyncio
    async def test_add_global_challenge_with_null_challenged_id(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        challenger = await _seed_player(uow, tg_id=1)
        assert challenger.id is not None
        repo = SqlAlchemyDuelRepository(uow=uow)

        challenge = _build_global_challenge(challenger_id=challenger.id)
        async with uow:
            stored = await repo.add(challenge)

        assert stored.id is not None
        assert stored.challenged_id is None
        assert stored.mode is DuelMode.GLOBAL_ONLY

    @pytest.mark.asyncio
    async def test_get_by_id_returns_pending_challenge(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        challenger = await _seed_player(uow, tg_id=1)
        challenged = await _seed_player(uow, tg_id=2)
        assert challenger.id is not None
        assert challenged.id is not None
        repo = SqlAlchemyDuelRepository(uow=uow)

        async with uow:
            stored = await repo.add(
                _build_chat_challenge(
                    challenger_id=challenger.id,
                    challenged_id=challenged.id,
                ),
            )
        assert stored.id is not None

        async with uow:
            loaded = await repo.get_by_id(duel_id=stored.id)
        assert loaded is not None
        assert loaded == stored

    @pytest.mark.asyncio
    async def test_get_by_id_missing_returns_none(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyDuelRepository(uow=uow)
        async with uow:
            assert await repo.get_by_id(duel_id=99999) is None

    @pytest.mark.asyncio
    async def test_add_with_preset_id_rejected(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        challenger = await _seed_player(uow, tg_id=1)
        challenged = await _seed_player(uow, tg_id=2)
        assert challenger.id is not None
        assert challenged.id is not None
        repo = SqlAlchemyDuelRepository(uow=uow)

        async with uow:
            stored = await repo.add(
                _build_chat_challenge(
                    challenger_id=challenger.id,
                    challenged_id=challenged.id,
                ),
            )

        with pytest.raises(DomainIntegrityError, match="pre-set id"):
            async with uow:
                await repo.add(stored)

    @pytest.mark.asyncio
    async def test_save_without_id_rejected(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyDuelRepository(uow=uow)
        challenge = _build_chat_challenge(challenger_id=1, challenged_id=2)
        with pytest.raises(DomainIntegrityError, match="requires id"):
            async with uow:
                await repo.save(challenge)

    @pytest.mark.asyncio
    async def test_save_unknown_id_raises(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyDuelRepository(uow=uow)
        ghost = _build_chat_challenge(challenger_id=1, challenged_id=2)
        ghost_with_id = replace(ghost, id=99999)
        with pytest.raises(DomainIntegrityError, match="not found"):
            async with uow:
                await repo.save(ghost_with_id)


class TestCancelPersistence:
    @pytest.mark.asyncio
    async def test_cancel_persists_state_and_timestamp(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        challenger = await _seed_player(uow, tg_id=1)
        challenged = await _seed_player(uow, tg_id=2)
        assert challenger.id is not None
        assert challenged.id is not None
        repo = SqlAlchemyDuelRepository(uow=uow)

        async with uow:
            stored = await repo.add(
                _build_chat_challenge(
                    challenger_id=challenger.id,
                    challenged_id=challenged.id,
                ),
            )
        assert stored.id is not None

        cancelled_at = NOW + timedelta(minutes=5)
        async with uow:
            saved = await repo.save(stored.cancel(now=cancelled_at))

        assert saved.state is DuelState.CANCELLED
        assert saved.cancelled_at == cancelled_at

        async with uow:
            loaded = await repo.get_by_id(duel_id=stored.id)
        assert loaded is not None
        assert loaded.state is DuelState.CANCELLED
        assert loaded.cancelled_at == cancelled_at


class TestAcceptPersistence:
    @pytest.mark.asyncio
    async def test_chat_accept_captures_lengths_and_starts_round_one(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        challenger = await _seed_player(uow, tg_id=1)
        challenged = await _seed_player(uow, tg_id=2)
        assert challenger.id is not None
        assert challenged.id is not None
        repo = SqlAlchemyDuelRepository(uow=uow)

        async with uow:
            stored = await repo.add(
                _build_chat_challenge(
                    challenger_id=challenger.id,
                    challenged_id=challenged.id,
                ),
            )
        assert stored.id is not None

        accepted_at = NOW + timedelta(minutes=1)
        accepted = stored.accept(
            accepter_id=challenged.id,
            p1_length_cm=100,
            p2_length_cm=80,
            now=accepted_at,
        )
        async with uow:
            saved = await repo.save(accepted)

        assert saved.state is DuelState.IN_PROGRESS
        assert saved.accepted_at == accepted_at
        assert saved.p1_initial_length_cm == 100
        assert saved.p2_initial_length_cm == 80
        assert saved.pending_round is not None
        assert saved.pending_round.round_num == 1
        assert saved.pending_round.p1_choice is None
        assert saved.pending_round.p2_choice is None

        async with uow:
            loaded = await repo.get_by_id(duel_id=stored.id)
        assert loaded is not None
        assert loaded == saved

    @pytest.mark.asyncio
    async def test_global_accept_sets_challenged_id(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        challenger = await _seed_player(uow, tg_id=1)
        accepter = await _seed_player(uow, tg_id=2)
        assert challenger.id is not None
        assert accepter.id is not None
        repo = SqlAlchemyDuelRepository(uow=uow)

        async with uow:
            stored = await repo.add(_build_global_challenge(challenger_id=challenger.id))
        assert stored.id is not None
        assert stored.challenged_id is None

        accepted = stored.accept(
            accepter_id=accepter.id,
            p1_length_cm=100,
            p2_length_cm=80,
            now=NOW + timedelta(minutes=1),
        )
        async with uow:
            saved = await repo.save(accepted)
        assert saved.challenged_id == accepter.id

        async with uow:
            loaded = await repo.get_by_id(duel_id=stored.id)
        assert loaded is not None
        assert loaded.challenged_id == accepter.id


class TestSubmitMovePersistence:
    @pytest.mark.asyncio
    async def test_partial_pending_round_persists_only_one_side(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        challenger = await _seed_player(uow, tg_id=1)
        challenged = await _seed_player(uow, tg_id=2)
        assert challenger.id is not None
        assert challenged.id is not None
        repo = SqlAlchemyDuelRepository(uow=uow)

        async with uow:
            stored = await repo.add(
                _build_chat_challenge(
                    challenger_id=challenger.id,
                    challenged_id=challenged.id,
                ),
            )
        accepted = stored.accept(
            accepter_id=challenged.id,
            p1_length_cm=100,
            p2_length_cm=80,
            now=NOW + timedelta(minutes=1),
        )
        async with uow:
            after_accept = await repo.save(accepted)
        assert after_accept.id is not None

        # Только p1 отправляет ход.
        with_p1 = after_accept.submit_move(
            player_id=challenger.id,
            choice=_ch(Position.HIGH, Position.LOW),
            now=NOW + timedelta(minutes=2),
        )
        async with uow:
            saved = await repo.save(with_p1)

        assert saved.pending_round is not None
        assert saved.pending_round.round_num == 1
        assert saved.pending_round.p1_choice == _ch(Position.HIGH, Position.LOW)
        assert saved.pending_round.p2_choice is None
        assert saved.completed_rounds == ()

        async with uow:
            loaded = await repo.get_by_id(duel_id=after_accept.id)
        assert loaded is not None
        assert loaded == saved

    @pytest.mark.asyncio
    async def test_round_auto_resolves_when_both_submitted(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        challenger = await _seed_player(uow, tg_id=1)
        challenged = await _seed_player(uow, tg_id=2)
        assert challenger.id is not None
        assert challenged.id is not None
        repo = SqlAlchemyDuelRepository(uow=uow)

        async with uow:
            stored = await repo.add(
                _build_chat_challenge(
                    challenger_id=challenger.id,
                    challenged_id=challenged.id,
                ),
            )
        accepted = stored.accept(
            accepter_id=challenged.id,
            p1_length_cm=100,
            p2_length_cm=80,
            now=NOW + timedelta(minutes=1),
        )

        # p1 атакует HIGH, блокирует LOW. p2 атакует LOW (попадает в блок),
        # блокирует MID (атака p1 пробивает).
        after_p1 = accepted.submit_move(
            player_id=challenger.id,
            choice=_ch(Position.HIGH, Position.LOW),
            now=NOW + timedelta(minutes=2),
        )
        after_p2 = after_p1.submit_move(
            player_id=challenged.id,
            choice=_ch(Position.LOW, Position.MID),
            now=NOW + timedelta(minutes=3),
        )
        async with uow:
            saved = await repo.save(after_p2)

        # Раунд закрылся → completed_rounds[0] заполнен, pending_round → 2.
        assert len(saved.completed_rounds) == 1
        assert saved.pending_round is not None
        assert saved.pending_round.round_num == 2
        assert saved.pending_round.p1_choice is None
        assert saved.pending_round.p2_choice is None

        round_1 = saved.completed_rounds[0]
        assert round_1.p1_choice == _ch(Position.HIGH, Position.LOW)
        assert round_1.p2_choice == _ch(Position.LOW, Position.MID)
        # p1.attack=HIGH vs p2.block=MID → пробитие, damage = floor(80*10/100)=8.
        assert round_1.p1_attack_blocked is False
        assert round_1.p1_damage_to_p2 == 8
        # p2.attack=LOW vs p1.block=LOW → блок, damage=0.
        assert round_1.p2_attack_blocked is True
        assert round_1.p2_damage_to_p1 == 0

        async with uow:
            loaded = await repo.get_by_id(duel_id=saved.id) if saved.id is not None else None
        assert loaded is not None
        assert loaded == saved


class TestFullDuelPersistence:
    @pytest.mark.asyncio
    async def test_full_3_round_duel_completes(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        challenger = await _seed_player(uow, tg_id=1)
        challenged = await _seed_player(uow, tg_id=2)
        assert challenger.id is not None
        assert challenged.id is not None
        repo = SqlAlchemyDuelRepository(uow=uow)

        # Создаём + accept-им + проводим 3 раунда — все save-ы по очереди.
        async with uow:
            stored = await repo.add(
                _build_chat_challenge(
                    challenger_id=challenger.id,
                    challenged_id=challenged.id,
                ),
            )
        assert stored.id is not None

        accepted = stored.accept(
            accepter_id=challenged.id,
            p1_length_cm=100,
            p2_length_cm=100,
            now=NOW + timedelta(minutes=1),
        )
        async with uow:
            duel = await repo.save(accepted)

        # Раунд 1: p1 пробивает (HIGH vs MID), p2 блокируется (LOW vs LOW).
        # damage: p1→p2 = 100*10/100 = 10, p2→p1 = 0.
        d1 = duel.submit_move(
            player_id=challenger.id,
            choice=_ch(Position.HIGH, Position.LOW),
            now=NOW + timedelta(minutes=2),
        )
        d1 = d1.submit_move(
            player_id=challenged.id,
            choice=_ch(Position.LOW, Position.MID),
            now=NOW + timedelta(minutes=3),
        )
        async with uow:
            duel = await repo.save(d1)
        assert len(duel.completed_rounds) == 1

        # Раунд 2: симметрично.
        d2 = duel.submit_move(
            player_id=challenger.id,
            choice=_ch(Position.MID, Position.HIGH),
            now=NOW + timedelta(minutes=4),
        )
        d2 = d2.submit_move(
            player_id=challenged.id,
            choice=_ch(Position.HIGH, Position.LOW),
            now=NOW + timedelta(minutes=5),
        )
        async with uow:
            duel = await repo.save(d2)
        assert len(duel.completed_rounds) == 2

        # Раунд 3.
        d3 = duel.submit_move(
            player_id=challenger.id,
            choice=_ch(Position.LOW, Position.MID),
            now=NOW + timedelta(minutes=6),
        )
        d3 = d3.submit_move(
            player_id=challenged.id,
            choice=_ch(Position.MID, Position.HIGH),
            now=NOW + timedelta(minutes=7),
        )
        async with uow:
            duel = await repo.save(d3)

        assert duel.state is DuelState.COMPLETED
        assert duel.completed_at is not None
        assert duel.pending_round is None
        assert duel.final_outcome is not None
        # p1 пробил все 3 раунда по 10 cm = 30; p2 — все 3 заблокирован.
        assert duel.final_outcome.p1_total_dealt == 30
        assert duel.final_outcome.p2_total_dealt == 0
        assert duel.final_outcome.p1_delta_cm == 30
        assert duel.final_outcome.p2_delta_cm == -30
        assert duel.final_outcome.winner is DuelWinner.P1

        # Полная перезагрузка с диска.
        async with uow:
            loaded = await repo.get_by_id(duel_id=duel.id) if duel.id is not None else None
        assert loaded is not None
        assert loaded == duel
        assert len(loaded.completed_rounds) == 3
        assert loaded.final_outcome is not None
        assert loaded.final_outcome.winner is DuelWinner.P1


class TestSelfChallengeDbConstraint:
    @pytest.mark.asyncio
    async def test_db_check_blocks_self_challenge_via_raw_replace(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """CHECK ck_pvp_duels_no_self_challenge — last-line-of-defense.

        Доменный `Duel.create_challenge` уже бросает
        `SelfChallengeError` для CHAT-режимов; этот тест эмулирует
        обход домена (например, ручной SQL) через `dataclasses.replace`
        и проверяет, что БД-уровневый CHECK всё равно не пустит запись.
        """
        challenger = await _seed_player(uow, tg_id=1)
        challenged = await _seed_player(uow, tg_id=2)
        assert challenger.id is not None
        assert challenged.id is not None
        repo = SqlAlchemyDuelRepository(uow=uow)

        challenge = _build_chat_challenge(
            challenger_id=challenger.id,
            challenged_id=challenged.id,
        )
        # Подменяем challenged_id на самого challenger-а (имитация обхода домена).
        evil = replace(challenge, challenged_id=challenger.id)
        with pytest.raises(DomainIntegrityError):
            async with uow:
                await repo.add(evil)
