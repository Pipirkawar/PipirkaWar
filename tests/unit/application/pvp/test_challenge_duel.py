"""Unit-тесты `ChallengeDuel` (Спринт 2.1.D)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.dto.inputs import ChallengeDuelInput
from pipirik_wars.application.pvp import ChallengeDuel, DuelChallenged
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.player import Length, PlayerNotFoundError
from pipirik_wars.domain.progression.errors import AnticheatSoftBanError
from pipirik_wars.domain.pvp import (
    DuelMode,
    DuelState,
    PvpRequirementsNotMetError,
    SelfChallengeError,
)
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.security.errors import LockAlreadyHeldError
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakeDuelRepository,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.application.pvp._helpers import seed_pvp_eligible_player
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


def _build() -> tuple[
    ChallengeDuel,
    FakePlayerRepository,
    FakeDuelRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeActivityLockRepository,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    duels = FakeDuelRepository()
    audit = FakeAuditLogger()
    clock = FakeClock(_NOW)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=clock)
    balance = FakeBalanceConfig(build_valid_balance())
    use_case = ChallengeDuel(
        uow=uow,
        players=players,
        duels=duels,
        locks=locks,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    return use_case, players, duels, audit, uow, lock_repo, clock


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_chat_then_global_creates_pending_duel(self) -> None:
        use_case, players, duels, audit, uow, lock_repo, _clock = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert challenged.id is not None

        result = await use_case.execute(
            ChallengeDuelInput(
                challenger_tg_id=1,
                challenged_tg_id=2,
                mode="chat_then_global",
            )
        )

        assert isinstance(result, DuelChallenged)
        duel = result.duel
        assert duel.id == 1
        assert duel.state is DuelState.PENDING_ACCEPT
        assert duel.mode is DuelMode.CHAT_THEN_GLOBAL
        assert duel.challenger_id == challenger.id
        assert duel.challenged_id == challenged.id
        assert duel.created_at == _NOW
        assert duel.hit_pct == 10  # из дефолтного balance
        assert duel.expected_rounds == 3

        # лок только на челленджера; оппонент берётся в AcceptDuel
        assert lock_repo.locks[("player", challenger.id)].reason is LockReason.PVP
        assert ("player", challenged.id) not in lock_repo.locks

        assert uow.commits == 1
        assert uow.rollbacks == 0
        assert len(duels.rows) == 1

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.PVP_DUEL_CREATED
        assert entry.target_kind == "pvp_duel"
        assert entry.target_id == "1"
        assert entry.idempotency_key == "pvp_duel_created:1"
        assert entry.actor_id == challenger.tg_id

    @pytest.mark.asyncio
    async def test_global_only_without_challenged(self) -> None:
        use_case, players, duels, _audit, _uow, _lock_repo, _clock = _build()
        await seed_pvp_eligible_player(players, tg_id=1)

        result = await use_case.execute(
            ChallengeDuelInput(
                challenger_tg_id=1,
                challenged_tg_id=None,
                mode="global_only",
            )
        )

        assert result.duel.mode is DuelMode.GLOBAL_ONLY
        assert result.duel.challenged_id is None
        assert len(duels.rows) == 1

    @pytest.mark.asyncio
    async def test_chat_only_creates_targeted_challenge(self) -> None:
        use_case, players, _duels, _audit, _uow, _lock_repo, _clock = _build()
        await seed_pvp_eligible_player(players, tg_id=1)
        await seed_pvp_eligible_player(players, tg_id=2, username="bob")

        result = await use_case.execute(
            ChallengeDuelInput(
                challenger_tg_id=1,
                challenged_tg_id=2,
                mode="chat_only",
            )
        )

        assert result.duel.mode is DuelMode.CHAT_ONLY


class TestErrors:
    @pytest.mark.asyncio
    async def test_player_not_found(self) -> None:
        use_case, _p, _d, _a, uow, _l, _c = _build()
        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(ChallengeDuelInput(challenger_tg_id=999, mode="global_only"))
        # transaction rolled back
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_challenged_not_found(self) -> None:
        use_case, players, _d, _a, _uow, _l, _c = _build()
        await seed_pvp_eligible_player(players, tg_id=1)
        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(
                ChallengeDuelInput(
                    challenger_tg_id=1,
                    challenged_tg_id=999,
                    mode="chat_only",
                )
            )

    @pytest.mark.asyncio
    async def test_self_challenge_rejected(self) -> None:
        use_case, players, _d, _a, _uow, _l, _c = _build()
        await seed_pvp_eligible_player(players, tg_id=1)
        with pytest.raises(SelfChallengeError):
            await use_case.execute(
                ChallengeDuelInput(challenger_tg_id=1, challenged_tg_id=1, mode="chat_only")
            )

    @pytest.mark.asyncio
    async def test_length_below_min(self) -> None:
        use_case, players, _d, _a, uow, _l, _c = _build()
        # длина 5 < min_length_cm=20
        await seed_pvp_eligible_player(players, tg_id=1, length_cm=5)
        with pytest.raises(PvpRequirementsNotMetError) as exc:
            await use_case.execute(ChallengeDuelInput(challenger_tg_id=1, mode="global_only"))
        assert exc.value.requirement == "length"
        assert exc.value.required == 20
        assert exc.value.actual == 5
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_thickness_below_min(self) -> None:
        use_case, players, _d, _a, _uow, _l, _c = _build()
        # thickness 1 < min_thickness_level=2
        await seed_pvp_eligible_player(players, tg_id=1, thickness_level=1)
        with pytest.raises(PvpRequirementsNotMetError) as exc:
            await use_case.execute(ChallengeDuelInput(challenger_tg_id=1, mode="global_only"))
        assert exc.value.requirement == "thickness"

    @pytest.mark.asyncio
    async def test_anticheat_soft_ban(self) -> None:
        use_case, players, _d, _a, _uow, _l, _c = _build()
        ban_until = _NOW.replace(year=2026, month=6)
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        banned = challenger.with_anticheat_ban(until=ban_until, now=_NOW)
        await players.save(banned)
        with pytest.raises(AnticheatSoftBanError):
            await use_case.execute(ChallengeDuelInput(challenger_tg_id=1, mode="global_only"))

    @pytest.mark.asyncio
    async def test_already_locked(self) -> None:
        use_case, players, _d, _a, uow, lock_repo, _c = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        assert challenger.id is not None
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=challenger.id,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_NOW.replace(hour=23),
        )
        with pytest.raises(LockAlreadyHeldError):
            await use_case.execute(ChallengeDuelInput(challenger_tg_id=1, mode="global_only"))
        # лок не снят (другой reason), commit отката
        assert lock_repo.locks[("player", challenger.id)].reason is LockReason.FOREST
        assert uow.commits == 0
        assert uow.rollbacks == 1

    def test_global_only_with_challenged_id_dto_rejects(self) -> None:
        # Pydantic-валидатор DTO ловит несовместимое сочетание мод+target.
        with pytest.raises(ValueError):
            ChallengeDuelInput(
                challenger_tg_id=1,
                challenged_tg_id=2,
                mode="global_only",
            )

    def test_chat_only_without_challenged_id_dto_rejects(self) -> None:
        with pytest.raises(ValueError):
            ChallengeDuelInput(challenger_tg_id=1, challenged_tg_id=None, mode="chat_only")


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_length_exactly_at_min(self) -> None:
        # длина ровно min_length_cm — допускается (≥, не >).
        use_case, players, _d, _a, _uow, _l, _c = _build()
        # min=20
        challenger = await seed_pvp_eligible_player(players, tg_id=1, length_cm=20)
        result = await use_case.execute(ChallengeDuelInput(challenger_tg_id=1, mode="global_only"))
        assert result.duel.id is not None
        assert challenger.length == Length(cm=20)
