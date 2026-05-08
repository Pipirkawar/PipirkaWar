"""Unit-тесты `CreateCaravan` (Спринт 3.2-B, ГДД §9.1 — §9.3).

Покрытие:
- happy-path: лидер клана-отправителя создаёт караван;
- audit `CARAVAN_CREATED` с idempotency-key;
- лок берётся, scheduler `caravan_lobby_close` запланирован;
- участник-лидер сохранён как `CARAVANEER` + `is_leader=True` + `contribution`;
- ошибки: clan не найден, clan заморожен, player не найден, player заморожен,
  не лидер клана, член другого клана, member-роль (не лидер),
  thickness < 7, длина после взноса < 20 см, активный караван уже есть,
  кулдаун клана не истёк, лок не взять (дублирующийся).
"""

from __future__ import annotations

from dataclasses import replace as dc_replace
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.caravans import CaravanCreated, CreateCaravan
from pipirik_wars.application.dto.inputs import CreateCaravanInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.caravan import (
    AlreadyInCaravanError,
    Caravan,
    CaravanCooldownError,
    CaravanRequirementError,
    CaravanRole,
    CaravanRoleConflictError,
    CaravanStatus,
)
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanFrozenError,
    ClanMember,
    ClanMemberRole,
    ClanTitle,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    Thickness,
    Username,
)
from pipirik_wars.domain.player.errors import PlayerFrozenError
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.shared.errors import IntegrityError
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeCaravanParticipantRepository,
    FakeCaravanRepository,
    FakeClanMembershipRepository,
    FakeClanRepository,
    FakeClock,
    FakeDelayedJobScheduler,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_SENDER_CHAT_ID = -100123
_RECEIVER_CHAT_ID = -100456


def _build_use_case(
    *,
    seed: int = 12345,
    clock: FakeClock | None = None,
) -> tuple[
    CreateCaravan,
    FakeUnitOfWork,
    FakeClanRepository,
    FakeClanMembershipRepository,
    FakePlayerRepository,
    FakeCaravanRepository,
    FakeCaravanParticipantRepository,
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeClock,
    FakeDelayedJobScheduler,
]:
    uow = FakeUnitOfWork()
    clans = FakeClanRepository()
    members = FakeClanMembershipRepository()
    players = FakePlayerRepository()
    caravans = FakeCaravanRepository()
    participants = FakeCaravanParticipantRepository()
    lock_repo = FakeActivityLockRepository()
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(_NOW)
    rng = FakeRandom(seed=seed)
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    balance = FakeBalanceConfig(build_valid_balance())
    scheduler = FakeDelayedJobScheduler()
    use_case = CreateCaravan(
        uow=uow,
        clans=clans,
        clan_members=members,
        players=players,
        caravans=caravans,
        caravan_participants=participants,
        locks=locks,
        balance=balance,
        random=rng,
        audit=audit,
        clock=used_clock,
        scheduler=scheduler,
    )
    return (
        use_case,
        uow,
        clans,
        members,
        players,
        caravans,
        participants,
        lock_repo,
        audit,
        used_clock,
        scheduler,
    )


async def _seed_clan(
    clans: FakeClanRepository,
    *,
    chat_id: int,
    title: str,
) -> Clan:
    fresh = Clan.new(
        chat_id=chat_id,
        chat_kind=ChatKind.SUPERGROUP,
        title=ClanTitle(value=title),
        now=_NOW,
    )
    return await clans.add(fresh)


async def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str = "leader",
    length_cm: int = 100,
    thickness_level: int = 7,
) -> Player:
    fresh = Player.new(tg_id=tg_id, username=Username(value=username), now=_NOW)
    persisted = await players.add(fresh)
    upgraded = persisted.with_thickness(Thickness(level=thickness_level), now=_NOW).with_length(
        Length(cm=length_cm), now=_NOW
    )
    return await players.save(upgraded)


async def _seed_member(
    members: FakeClanMembershipRepository,
    *,
    clan_id: int,
    player_id: int,
    role: ClanMemberRole = ClanMemberRole.LEADER,
) -> ClanMember:
    fresh = ClanMember.new(clan_id=clan_id, player_id=player_id, role=role, now=_NOW)
    return await members.add(fresh)


def _input(*, contribution_cm: int = 10, initiator_tg_id: int = 42) -> CreateCaravanInput:
    return CreateCaravanInput(
        initiator_tg_id=initiator_tg_id,
        sender_chat_id=_SENDER_CHAT_ID,
        receiver_chat_id=_RECEIVER_CHAT_ID,
        contribution_cm=contribution_cm,
    )


async def _seed_happy_path(
    *,
    clans: FakeClanRepository,
    members: FakeClanMembershipRepository,
    players: FakePlayerRepository,
    leader_thickness: int = 7,
    leader_length_cm: int = 100,
) -> tuple[Clan, Clan, Player]:
    sender = await _seed_clan(clans, chat_id=_SENDER_CHAT_ID, title="Senders")
    receiver = await _seed_clan(clans, chat_id=_RECEIVER_CHAT_ID, title="Receivers")
    leader = await _seed_player(
        players,
        tg_id=42,
        length_cm=leader_length_cm,
        thickness_level=leader_thickness,
    )
    assert sender.id is not None
    assert leader.id is not None
    await _seed_member(
        members,
        clan_id=sender.id,
        player_id=leader.id,
        role=ClanMemberRole.LEADER,
    )
    return sender, receiver, leader


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_creates_caravan_and_leader_participant(self) -> None:
        (
            use_case,
            uow,
            clans,
            members,
            players,
            caravans,
            participants,
            _lock_repo,
            _audit,
            clock,
            scheduler,
        ) = _build_use_case()
        sender, receiver, leader = await _seed_happy_path(
            clans=clans, members=members, players=players
        )

        result = await use_case.execute(_input(contribution_cm=10))

        assert isinstance(result, CaravanCreated)
        caravan = result.caravan
        assert caravan.id == 1
        assert caravan.sender_clan_id == sender.id
        assert caravan.receiver_clan_id == receiver.id
        assert caravan.leader_player_id == leader.id
        assert caravan.status is CaravanStatus.LOBBY
        assert caravan.started_at == clock.now()
        cfg = build_valid_balance().caravans
        assert caravan.lobby_ends_at == clock.now() + timedelta(minutes=cfg.lobby_minutes)
        assert caravan.battle_ends_at == caravan.lobby_ends_at + timedelta(
            minutes=cfg.battle_minutes
        )
        assert len(caravans.rows) == 1
        # Лидер-участник сохранён.
        assert len(participants.rows) == 1
        leader_participant = participants.rows[0]
        assert leader_participant.role is CaravanRole.CARAVANEER
        assert leader_participant.is_leader is True
        assert leader_participant.contribution is not None
        assert leader_participant.contribution.cm == 10
        assert leader_participant.player_id == leader.id
        # Транзакция коммитится ровно раз.
        assert uow.commits == 1
        assert uow.rollbacks == 0
        # Лобби-close-job запланирован на `lobby_ends_at`.
        assert scheduler.scheduled_caravan_lobby_close[caravan.id].run_at == (caravan.lobby_ends_at)

    @pytest.mark.asyncio
    async def test_lock_taken_with_caravan_reason(self) -> None:
        (
            use_case,
            _uow,
            clans,
            members,
            players,
            _caravans,
            _participants,
            lock_repo,
            _audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        _sender, _receiver, leader = await _seed_happy_path(
            clans=clans, members=members, players=players
        )

        await use_case.execute(_input())

        assert leader.id is not None
        lock = await lock_repo.get(actor_kind="player", actor_id=leader.id)
        assert lock is not None
        assert lock.reason is LockReason.CARAVAN

    @pytest.mark.asyncio
    async def test_random_seed_persisted(self) -> None:
        (
            use_case,
            _uow,
            clans,
            members,
            players,
            caravans,
            _participants,
            _lock_repo,
            _audit,
            _clock,
            _scheduler,
        ) = _build_use_case(seed=999)
        await _seed_happy_path(clans=clans, members=members, players=players)

        await use_case.execute(_input())

        assert len(caravans.rows) == 1
        assert caravans.rows[0].random_seed > 0
        assert caravans.rows[0].random_seed < 2**31


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_caravan_created(self) -> None:
        (
            use_case,
            _uow,
            clans,
            members,
            players,
            _caravans,
            _participants,
            _lock_repo,
            audit,
            clock,
            _scheduler,
        ) = _build_use_case()
        sender, receiver, leader = await _seed_happy_path(
            clans=clans, members=members, players=players
        )

        result = await use_case.execute(_input(contribution_cm=15))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.CARAVAN_CREATED
        assert entry.actor_id == 42
        assert entry.target_kind == "caravan"
        assert entry.target_id == str(result.caravan.id)
        assert entry.before is None
        assert entry.after is not None
        assert entry.after["sender_clan_id"] == sender.id
        assert entry.after["receiver_clan_id"] == receiver.id
        assert entry.after["leader_player_id"] == leader.id
        assert entry.after["leader_contribution_cm"] == 15
        assert entry.idempotency_key == f"caravan_created:{result.caravan.id}"
        assert entry.occurred_at == clock.now()


class TestErrors:
    @pytest.mark.asyncio
    async def test_sender_clan_not_registered_raises_integrity(self) -> None:
        (
            use_case,
            uow,
            clans,
            _members,
            _players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        # Только receiver зарегистрирован — sender отсутствует.
        await _seed_clan(clans, chat_id=_RECEIVER_CHAT_ID, title="Receivers")

        with pytest.raises(IntegrityError):
            await use_case.execute(_input())

        assert caravans.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1
        assert uow.commits == 0

    @pytest.mark.asyncio
    async def test_receiver_clan_not_registered_raises_integrity(self) -> None:
        (
            use_case,
            uow,
            clans,
            _members,
            _players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        await _seed_clan(clans, chat_id=_SENDER_CHAT_ID, title="Senders")

        with pytest.raises(IntegrityError):
            await use_case.execute(_input())

        assert caravans.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_sender_clan_frozen_raises(self) -> None:
        (
            use_case,
            uow,
            clans,
            members,
            players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        sender, _receiver, _leader = await _seed_happy_path(
            clans=clans, members=members, players=players
        )
        assert sender.id is not None
        await clans.save(sender.freeze(now=_NOW))

        with pytest.raises(ClanFrozenError):
            await use_case.execute(_input())

        assert caravans.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_receiver_clan_frozen_raises(self) -> None:
        (
            use_case,
            uow,
            clans,
            members,
            players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        _sender, receiver, _leader = await _seed_happy_path(
            clans=clans, members=members, players=players
        )
        assert receiver.id is not None
        await clans.save(receiver.freeze(now=_NOW))

        with pytest.raises(ClanFrozenError):
            await use_case.execute(_input())

        assert caravans.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_found_raises(self) -> None:
        (
            use_case,
            uow,
            clans,
            _members,
            _players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        await _seed_clan(clans, chat_id=_SENDER_CHAT_ID, title="Senders")
        await _seed_clan(clans, chat_id=_RECEIVER_CHAT_ID, title="Receivers")

        with pytest.raises(PlayerNotFoundError) as exc:
            await use_case.execute(_input())

        assert exc.value.tg_id == 42
        assert caravans.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_frozen_raises(self) -> None:
        (
            use_case,
            uow,
            clans,
            members,
            players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        _sender, _receiver, leader = await _seed_happy_path(
            clans=clans, members=members, players=players
        )
        frozen = leader.freeze(now=_NOW)
        await players.save(frozen)

        with pytest.raises(PlayerFrozenError) as exc:
            await use_case.execute(_input())

        assert exc.value.tg_id == 42
        assert caravans.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_in_sender_clan_raises_role_conflict(self) -> None:
        (
            use_case,
            uow,
            clans,
            _members,
            players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        await _seed_clan(clans, chat_id=_SENDER_CHAT_ID, title="Senders")
        await _seed_clan(clans, chat_id=_RECEIVER_CHAT_ID, title="Receivers")
        await _seed_player(players, tg_id=42)
        # Игрок без членства.

        with pytest.raises(CaravanRoleConflictError) as exc:
            await use_case.execute(_input())

        assert exc.value.attempted_role == "leader"
        assert "not a member" in exc.value.reason
        assert caravans.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_in_other_clan_raises_role_conflict(self) -> None:
        (
            use_case,
            uow,
            clans,
            members,
            players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        await _seed_clan(clans, chat_id=_SENDER_CHAT_ID, title="Senders")
        receiver = await _seed_clan(clans, chat_id=_RECEIVER_CHAT_ID, title="Receivers")
        leader = await _seed_player(players, tg_id=42)
        assert receiver.id is not None
        assert leader.id is not None
        # Игрок числится в receiver-клане, а не в sender-клане.
        await _seed_member(
            members,
            clan_id=receiver.id,
            player_id=leader.id,
            role=ClanMemberRole.LEADER,
        )

        with pytest.raises(CaravanRoleConflictError):
            await use_case.execute(_input())

        assert caravans.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_member_not_leader_raises_role_conflict(self) -> None:
        (
            use_case,
            uow,
            clans,
            members,
            players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        sender = await _seed_clan(clans, chat_id=_SENDER_CHAT_ID, title="Senders")
        await _seed_clan(clans, chat_id=_RECEIVER_CHAT_ID, title="Receivers")
        leader = await _seed_player(players, tg_id=42)
        assert sender.id is not None
        assert leader.id is not None
        await _seed_member(
            members,
            clan_id=sender.id,
            player_id=leader.id,
            role=ClanMemberRole.MEMBER,  # не LEADER
        )

        with pytest.raises(CaravanRoleConflictError) as exc:
            await use_case.execute(_input())

        assert exc.value.attempted_role == "leader"
        assert "expected 'leader'" in exc.value.reason
        assert caravans.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_thickness_below_required_raises(self) -> None:
        (
            use_case,
            uow,
            clans,
            members,
            players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        await _seed_happy_path(
            clans=clans,
            members=members,
            players=players,
            leader_thickness=6,  # требуется 7
        )

        with pytest.raises(CaravanRequirementError) as exc:
            await use_case.execute(_input())

        assert exc.value.requirement == "thickness"
        assert exc.value.required == 7
        assert exc.value.actual == 6
        assert caravans.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_length_after_contribution_below_required_raises(self) -> None:
        (
            use_case,
            uow,
            clans,
            members,
            players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        # length=25, contribution=10 → остаётся 15 (< 20)
        await _seed_happy_path(clans=clans, members=members, players=players, leader_length_cm=25)

        with pytest.raises(CaravanRequirementError) as exc:
            await use_case.execute(_input(contribution_cm=10))

        assert exc.value.requirement == "length_after_contribution"
        assert exc.value.required == 20
        assert exc.value.actual == 15
        assert caravans.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_active_caravan_already_exists_raises(self) -> None:
        (
            use_case,
            uow,
            clans,
            members,
            players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        sender, _receiver, _leader = await _seed_happy_path(
            clans=clans, members=members, players=players
        )
        # Первый караван — успешно.
        await use_case.execute(_input(contribution_cm=10))
        commits_after_first = uow.commits
        audit_after_first = len(audit.entries)
        # Второй "лидер" в том же клане (для unit-теста UNIQUE-лидерство
        # клана не интересует — `_ensure_player_is_clan_leader` смотрит
        # только на запись membership).
        leader2 = await _seed_player(
            players, tg_id=43, username="leader2", length_cm=100, thickness_level=7
        )
        assert leader2.id is not None
        assert sender.id is not None
        await _seed_member(
            members,
            clan_id=sender.id,
            player_id=leader2.id,
            role=ClanMemberRole.LEADER,
        )

        with pytest.raises(AlreadyInCaravanError) as exc:
            await use_case.execute(_input(contribution_cm=10, initiator_tg_id=43))

        assert exc.value.player_id == leader2.id
        # Второй караван не создался (только один — от первого вызова).
        assert len(caravans.rows) == 1
        # Первый успешный + один rollback.
        assert uow.commits == commits_after_first == 1
        assert uow.rollbacks == 1
        # audit — только один (от первого успешного).
        assert len(audit.entries) == audit_after_first == 1

    @pytest.mark.asyncio
    async def test_clan_cooldown_not_expired_raises(self) -> None:
        # Создаём караван, потом пытаемся создать ещё раз через час
        # (ожидаемый кулдаун — 12 часов).
        clock = FakeClock(_NOW)
        (
            use_case,
            uow,
            clans,
            members,
            players,
            caravans,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case(clock=clock)
        sender, _receiver, _leader = await _seed_happy_path(
            clans=clans, members=members, players=players
        )
        # Прошлый караван клана: статус FINISHED, но started_at недавно.
        # Используем низкоуровневую запись, чтобы обойти UNIQUE-инвариант
        # "active каравана" (FINISHED уже не активен).
        assert sender.id is not None
        prior = Caravan.starting(
            sender_clan_id=sender.id,
            receiver_clan_id=999,  # фиктивный, чтобы не пересекался
            leader_player_id=999,
            started_at=_NOW - timedelta(hours=1),
            lobby_ends_at=_NOW - timedelta(hours=1) + timedelta(minutes=20),
            battle_ends_at=_NOW - timedelta(hours=1) + timedelta(minutes=80),
            random_seed=1,
        )
        prior_finished = dc_replace(
            prior,
            id=99,
            status=CaravanStatus.FINISHED,
            finished_at=_NOW - timedelta(minutes=20),
        )
        caravans.rows.append(prior_finished)

        with pytest.raises(CaravanCooldownError) as exc:
            await use_case.execute(_input())

        assert exc.value.clan_id == sender.id
        assert exc.value.actual_remaining_seconds > 0
        # Кулдаун — 12 часов, прошёл 1 час → осталось ~11 часов.
        assert exc.value.actual_remaining_seconds <= 12 * 3600
        assert exc.value.actual_remaining_seconds >= 10 * 3600
        # Новый караван не создался (только prior_finished).
        assert len(caravans.rows) == 1
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_lock_already_held_raises_already_in_caravan(self) -> None:
        # Берём лок на лидере вручную (как будто он уже в другой активности),
        # и пытаемся создать караван.
        (
            use_case,
            uow,
            clans,
            members,
            players,
            caravans,
            _participants,
            lock_repo,
            audit,
            clock,
            _scheduler,
        ) = _build_use_case()
        _sender, _receiver, leader = await _seed_happy_path(
            clans=clans, members=members, players=players
        )
        assert leader.id is not None
        # Берём лок (PVE-deuelы или forest), чтобы acquire_lock в use-case
        # упал.
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=leader.id,
            reason=LockReason.FOREST,
            now=clock.now(),
            expires_at=clock.now() + timedelta(minutes=30),
        )

        with pytest.raises(AlreadyInCaravanError) as exc:
            await use_case.execute(_input())

        assert exc.value.player_id == leader.id
        assert caravans.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1
