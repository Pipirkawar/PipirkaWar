"""Unit-тесты `StartMassDuel` (Спринт 2.2.E)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from pipirik_wars.application.dto.inputs import StartMassDuelInput
from pipirik_wars.application.pvp import MassDuelStarted, StartMassDuel
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.clan import ClanFrozenError, ClanStatus
from pipirik_wars.domain.pvp import (
    MassDuel,
    MassDuelCooldownError,
    MassDuelNoParticipantsError,
    MassDuelState,
)
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.security.errors import LockAlreadyHeldError
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.shared.errors import IntegrityError
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClanMembershipRepository,
    FakeClanRepository,
    FakeClock,
    FakeMassDuelRepository,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.application.pvp._helpers import seed_pvp_eligible_player
from tests.unit.application.pvp._mass_helpers import (
    MASS_NOW,
    seed_clan,
    seed_clan_member,
    seed_eligible_clan_member,
)
from tests.unit.domain.balance.factories import build_valid_balance


def _build() -> tuple[
    StartMassDuel,
    FakePlayerRepository,
    FakeClanRepository,
    FakeClanMembershipRepository,
    FakeMassDuelRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeActivityLockRepository,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    clans = FakeClanRepository()
    members = FakeClanMembershipRepository()
    duels = FakeMassDuelRepository()
    audit = FakeAuditLogger()
    clock = FakeClock(MASS_NOW)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=clock)
    balance = FakeBalanceConfig(build_valid_balance())
    use_case = StartMassDuel(
        uow=uow,
        clans=clans,
        clan_members=members,
        players=players,
        duels=duels,
        locks=locks,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    return use_case, players, clans, members, duels, audit, uow, lock_repo, clock


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_two_clans_two_members_each_creates_in_progress_duel(self) -> None:
        use_case, players, clans, members, duels, audit, uow, lock_repo, _clock = _build()
        attacker_clan = await seed_clan(clans, chat_id=-100, title="Atk")
        defender_clan = await seed_clan(clans, chat_id=-200, title="Def")
        assert attacker_clan.id is not None
        assert defender_clan.id is not None

        a1 = await seed_eligible_clan_member(
            players=players,
            clan_members=members,
            clan_id=attacker_clan.id,
            tg_id=1,
            username="a1",
            length_cm=50,
        )
        a2 = await seed_eligible_clan_member(
            players=players,
            clan_members=members,
            clan_id=attacker_clan.id,
            tg_id=2,
            username="a2",
            length_cm=40,
        )
        d1 = await seed_eligible_clan_member(
            players=players,
            clan_members=members,
            clan_id=defender_clan.id,
            tg_id=3,
            username="d1",
            length_cm=60,
        )
        d2 = await seed_eligible_clan_member(
            players=players,
            clan_members=members,
            clan_id=defender_clan.id,
            tg_id=4,
            username="d2",
            length_cm=30,
        )

        result = await use_case.execute(
            StartMassDuelInput(
                initiator_tg_id=1,
                attacker_chat_id=-100,
                defender_chat_id=-200,
            )
        )

        assert isinstance(result, MassDuelStarted)
        duel = result.duel
        assert duel.id == 1
        assert duel.state is MassDuelState.IN_PROGRESS
        assert duel.clan1_id == attacker_clan.id
        assert duel.clan2_id == defender_clan.id
        assert sorted(duel.clan1_member_ids) == sorted([a1, a2])
        assert sorted(duel.clan2_member_ids) == sorted([d1, d2])
        assert duel.created_at == MASS_NOW
        assert duel.hit_pct == 10
        # Все участники под PvP-локом.
        for pid in (a1, a2, d1, d2):
            assert lock_repo.locks[("player", pid)].reason is LockReason.PVP

        assert uow.commits == 1
        assert uow.rollbacks == 0
        assert len(duels.rows) == 1

        # Audit-запись о создании.
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.PVP_MASS_DUEL_CREATED
        assert entry.target_kind == "pvp_mass_duel"
        assert entry.target_id == "1"
        assert entry.idempotency_key == "pvp_mass_duel_created:1"
        assert entry.actor_id == 1

    @pytest.mark.asyncio
    async def test_min_clan_members_one_per_side_is_enough(self) -> None:
        use_case, players, clans, members, duels, *_ = _build()
        atk = await seed_clan(clans, chat_id=-100, title="Atk")
        defc = await seed_clan(clans, chat_id=-200, title="Def")
        assert atk.id is not None
        assert defc.id is not None
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=atk.id, tg_id=1
        )
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=defc.id, tg_id=2, username="b"
        )

        result = await use_case.execute(
            StartMassDuelInput(
                initiator_tg_id=1,
                attacker_chat_id=-100,
                defender_chat_id=-200,
            )
        )
        assert result.duel.state is MassDuelState.IN_PROGRESS
        assert len(result.duel.clan1_member_ids) == 1
        assert len(result.duel.clan2_member_ids) == 1
        assert len(duels.rows) == 1


class TestEligibility:
    @pytest.mark.asyncio
    async def test_player_below_min_length_is_excluded(self) -> None:
        use_case, players, clans, members, *_ = _build()
        atk = await seed_clan(clans, chat_id=-100)
        defc = await seed_clan(clans, chat_id=-200)
        assert atk.id is not None and defc.id is not None
        # Атакующий клан: один eligible, один — короткий (length=10 < 20).
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=atk.id, tg_id=1
        )
        short_player = await seed_pvp_eligible_player(
            players, tg_id=2, length_cm=10, username="short"
        )
        assert short_player.id is not None
        await seed_clan_member(members, clan_id=atk.id, player_id=short_player.id)
        # Защитник нормальный.
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=defc.id, tg_id=3, username="d"
        )

        result = await use_case.execute(
            StartMassDuelInput(
                initiator_tg_id=1,
                attacker_chat_id=-100,
                defender_chat_id=-200,
            )
        )
        # Только один eligible-атакующий — short_player отфильтрован.
        assert len(result.duel.clan1_member_ids) == 1

    @pytest.mark.asyncio
    async def test_no_eligible_attackers_raises(self) -> None:
        use_case, players, clans, members, *_ = _build()
        atk = await seed_clan(clans, chat_id=-100)
        defc = await seed_clan(clans, chat_id=-200)
        assert atk.id is not None and defc.id is not None
        # У атакующего клана нет членов вообще.
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=defc.id, tg_id=1
        )

        with pytest.raises(MassDuelNoParticipantsError) as ei:
            await use_case.execute(
                StartMassDuelInput(
                    initiator_tg_id=1,
                    attacker_chat_id=-100,
                    defender_chat_id=-200,
                )
            )
        assert ei.value.clan_id == atk.id

    @pytest.mark.asyncio
    async def test_no_eligible_defenders_raises(self) -> None:
        use_case, players, clans, members, *_ = _build()
        atk = await seed_clan(clans, chat_id=-100)
        defc = await seed_clan(clans, chat_id=-200)
        assert atk.id is not None and defc.id is not None
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=atk.id, tg_id=1
        )
        # У защитника только короткий — отфильтруется.
        short = await seed_pvp_eligible_player(players, tg_id=2, length_cm=5, username="s")
        assert short.id is not None
        await seed_clan_member(members, clan_id=defc.id, player_id=short.id)

        with pytest.raises(MassDuelNoParticipantsError) as ei:
            await use_case.execute(
                StartMassDuelInput(
                    initiator_tg_id=1,
                    attacker_chat_id=-100,
                    defender_chat_id=-200,
                )
            )
        assert ei.value.clan_id == defc.id


class TestFrozenAndMissingClans:
    @pytest.mark.asyncio
    async def test_attacker_clan_unknown_raises_integrity(self) -> None:
        use_case, players, clans, members, *_ = _build()
        defc = await seed_clan(clans, chat_id=-200)
        assert defc.id is not None
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=defc.id, tg_id=1
        )
        with pytest.raises(IntegrityError):
            await use_case.execute(
                StartMassDuelInput(
                    initiator_tg_id=1,
                    attacker_chat_id=-100,  # не зарегистрирован
                    defender_chat_id=-200,
                )
            )

    @pytest.mark.asyncio
    async def test_attacker_clan_frozen_raises(self) -> None:
        use_case, players, clans, members, *_ = _build()
        atk = await seed_clan(clans, chat_id=-100)
        defc = await seed_clan(clans, chat_id=-200)
        assert atk.id is not None and defc.id is not None
        await clans.save(replace(atk, status=ClanStatus.FROZEN))
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=defc.id, tg_id=1
        )
        with pytest.raises(ClanFrozenError):
            await use_case.execute(
                StartMassDuelInput(
                    initiator_tg_id=1,
                    attacker_chat_id=-100,
                    defender_chat_id=-200,
                )
            )

    @pytest.mark.asyncio
    async def test_defender_clan_frozen_raises(self) -> None:
        use_case, players, clans, members, *_ = _build()
        atk = await seed_clan(clans, chat_id=-100)
        defc = await seed_clan(clans, chat_id=-200)
        assert atk.id is not None and defc.id is not None
        await clans.save(replace(defc, status=ClanStatus.FROZEN))
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=atk.id, tg_id=1
        )
        with pytest.raises(ClanFrozenError):
            await use_case.execute(
                StartMassDuelInput(
                    initiator_tg_id=1,
                    attacker_chat_id=-100,
                    defender_chat_id=-200,
                )
            )


class TestCooldown:
    @pytest.mark.asyncio
    async def test_recent_duel_attacker_blocks(self) -> None:
        use_case, players, clans, members, duels, *_ = _build()
        atk = await seed_clan(clans, chat_id=-100)
        defc = await seed_clan(clans, chat_id=-200)
        assert atk.id is not None and defc.id is not None
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=atk.id, tg_id=1
        )
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=defc.id, tg_id=2, username="d"
        )

        # Эмулируем недавно созданный duel у атакующего клана (1 час назад).
        recent = MassDuel.create_battle(
            clan1_id=atk.id,
            clan2_id=999,
            clan1_lengths={1: 50},
            clan2_lengths={888: 40},
            hit_pct=10,
            now=MASS_NOW - timedelta(hours=1),
        )
        await duels.add(recent)

        with pytest.raises(MassDuelCooldownError) as ei:
            await use_case.execute(
                StartMassDuelInput(
                    initiator_tg_id=1,
                    attacker_chat_id=-100,
                    defender_chat_id=-200,
                )
            )
        assert ei.value.clan_id == atk.id
        assert ei.value.cooldown_hours == 6

    @pytest.mark.asyncio
    async def test_old_duel_does_not_block(self) -> None:
        use_case, players, clans, members, duels, *_ = _build()
        atk = await seed_clan(clans, chat_id=-100)
        defc = await seed_clan(clans, chat_id=-200)
        assert atk.id is not None and defc.id is not None
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=atk.id, tg_id=1
        )
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=defc.id, tg_id=2, username="d"
        )

        old = MassDuel.create_battle(
            clan1_id=atk.id,
            clan2_id=999,
            clan1_lengths={1: 50},
            clan2_lengths={888: 40},
            hit_pct=10,
            now=MASS_NOW - timedelta(hours=10),
        )
        await duels.add(old)

        result = await use_case.execute(
            StartMassDuelInput(
                initiator_tg_id=1,
                attacker_chat_id=-100,
                defender_chat_id=-200,
            )
        )
        assert result.duel.state is MassDuelState.IN_PROGRESS


class TestLockConflicts:
    @pytest.mark.asyncio
    async def test_existing_lock_blocks_start(self) -> None:
        use_case, players, clans, members, _duels, _audit, _uow, lock_repo, _clock = _build()
        atk = await seed_clan(clans, chat_id=-100)
        defc = await seed_clan(clans, chat_id=-200)
        assert atk.id is not None and defc.id is not None
        a1 = await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=atk.id, tg_id=1
        )
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=defc.id, tg_id=2, username="d"
        )

        # Заранее берём лок на одного из атакующих.
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=a1,
            reason=LockReason.PVP,
            now=MASS_NOW,
            expires_at=MASS_NOW + timedelta(minutes=5),
        )

        with pytest.raises(LockAlreadyHeldError):
            await use_case.execute(
                StartMassDuelInput(
                    initiator_tg_id=1,
                    attacker_chat_id=-100,
                    defender_chat_id=-200,
                )
            )
