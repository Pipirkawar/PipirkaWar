"""Unit-тесты ``FreezePayouts`` / ``UnfreezePayouts`` (Спринт 4.1-E / Шаг E.7).

Покрытие:

* RBAC-flow: неактивный/неизвестный админ → ``AuthorizationError`` (без audit);
  активный, но недостаточная роль → ``AdminAuthorizationDeniedError`` +
  запись ``ADMIN_AUTHORIZATION_DENIED`` в admin-аудите.
* Happy-path: ``set_frozen(...)`` / ``set_unfrozen()`` + audit-запись
  ``ADMIN_FREEZE_PAYOUTS`` / ``ADMIN_UNFREEZE_PAYOUTS`` (один UoW-commit).
* Идемпотентность: повторный freeze того же админа той же причины — no-op
  (нет mutation, нет audit). Тот же админ с другой причиной /
  другой админ — пишем audit и обновляем state. Unfreeze на
  уже-unfrozen — no-op.
* Валидация: пустой ``reason`` для FreezePayouts → ``ValueError``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.monetization import (
    FreezePayouts,
    FreezePayoutsInput,
    UnfreezePayouts,
    UnfreezePayoutsInput,
)
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditSource,
    AdminAuthorizationDeniedError,
    AdminRole,
)
from pipirik_wars.domain.monetization.entities import PayoutFreeze
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll, FakeAdminAuthzDenyAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clock import FakeClock
from tests.fakes.payout_freeze_repo import FakePayoutFreezeRepository
from tests.fakes.uow import FakeUnitOfWork

_NOW = datetime(2026, 5, 12, 12, 0, 0, tzinfo=UTC)


def _build_freeze(
    *,
    authz: FakeAdminAuthzAllowAll | FakeAdminAuthzDenyAll | None = None,
    payout_freeze: FakePayoutFreezeRepository | None = None,
) -> tuple[
    FreezePayouts,
    FakeAdminRepository,
    FakePayoutFreezeRepository,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    repo = payout_freeze or FakePayoutFreezeRepository()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    return (
        FreezePayouts(
            uow=uow,
            admins=admins,
            payout_freeze_repo=repo,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=authz or FakeAdminAuthzAllowAll(),
        ),
        admins,
        repo,
        audit,
        uow,
    )


def _build_unfreeze(
    *,
    authz: FakeAdminAuthzAllowAll | FakeAdminAuthzDenyAll | None = None,
    payout_freeze: FakePayoutFreezeRepository | None = None,
) -> tuple[
    UnfreezePayouts,
    FakeAdminRepository,
    FakePayoutFreezeRepository,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    repo = payout_freeze or FakePayoutFreezeRepository()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    return (
        UnfreezePayouts(
            uow=uow,
            admins=admins,
            payout_freeze_repo=repo,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=authz or FakeAdminAuthzAllowAll(),
        ),
        admins,
        repo,
        audit,
        uow,
    )


@pytest.mark.asyncio
class TestFreezePayoutsAuthorization:
    async def test_unknown_actor_raises_authorization_error(self) -> None:
        uc, _admins, repo, audit, _uow = _build_freeze()

        with pytest.raises(AuthorizationError):
            await uc.execute(
                FreezePayoutsInput(actor_tg_id=99, reason="abuse detected"),
            )

        assert audit.entries == []
        assert repo.set_frozen_calls == []
        assert repo.state.is_frozen is False

    async def test_inactive_admin_raises(self) -> None:
        uc, admins, repo, audit, _uow = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN, is_active=False)

        with pytest.raises(AuthorizationError):
            await uc.execute(
                FreezePayoutsInput(actor_tg_id=42, reason="abuse"),
            )

        assert audit.entries == []
        assert repo.set_frozen_calls == []

    async def test_rbac_denied_writes_audit_and_no_mutation(self) -> None:
        uc, admins, repo, audit, _uow = _build_freeze(authz=FakeAdminAuthzDenyAll())
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        with pytest.raises(AdminAuthorizationDeniedError):
            await uc.execute(
                FreezePayoutsInput(
                    actor_tg_id=42,
                    reason="abuse",
                    tg_chat_id=-100,
                ),
            )

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AdminAuditAction.ADMIN_AUTHORIZATION_DENIED
        assert entry.target_kind == "payout_freeze"
        assert entry.target_id == "all"
        assert entry.tg_chat_id == -100
        assert repo.set_frozen_calls == []
        assert repo.state.is_frozen is False


@pytest.mark.asyncio
class TestFreezePayoutsValidation:
    async def test_empty_reason_raises(self) -> None:
        uc, admins, repo, audit, _uow = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        with pytest.raises(ValueError, match="non-empty"):
            await uc.execute(FreezePayoutsInput(actor_tg_id=42, reason="   "))

        assert audit.entries == []
        assert repo.set_frozen_calls == []


@pytest.mark.asyncio
class TestFreezePayoutsHappyPath:
    async def test_freezes_state_and_writes_audit(self) -> None:
        uc, admins, repo, audit, uow = _build_freeze()
        admin = admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        out = await uc.execute(
            FreezePayoutsInput(
                actor_tg_id=42,
                reason="suspicious payouts",
                tg_chat_id=-100,
            ),
        )

        assert out.is_frozen is True
        assert out.was_already_frozen is False

        assert repo.state.is_frozen is True
        assert repo.state.frozen_by_admin_id == admin.id
        assert repo.state.reason == "suspicious payouts"
        assert repo.state.frozen_at == _NOW

        assert len(repo.set_frozen_calls) == 1
        call = repo.set_frozen_calls[0]
        assert call.admin_id == admin.id
        assert call.at == _NOW
        assert call.reason == "suspicious payouts"

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AdminAuditAction.ADMIN_FREEZE_PAYOUTS
        assert entry.admin_id == admin.id
        assert entry.target_kind == "payout_freeze"
        assert entry.target_id == "all"
        assert entry.before == {
            "is_frozen": False,
            "frozen_by_admin_id": None,
            "reason": None,
        }
        assert entry.after == {
            "is_frozen": True,
            "frozen_by_admin_id": admin.id,
            "reason": "suspicious payouts",
        }
        assert entry.source is AdminAuditSource.BOT
        assert entry.tg_chat_id == -100
        assert entry.reason == "suspicious payouts"
        assert entry.idempotency_key is None
        assert entry.occurred_at == _NOW

        assert uow.commits == 1
        assert uow.rollbacks == 0

    async def test_reason_is_trimmed(self) -> None:
        uc, admins, repo, _audit, _uow = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        await uc.execute(
            FreezePayoutsInput(actor_tg_id=42, reason="  spaced reason  "),
        )

        assert repo.state.reason == "spaced reason"


@pytest.mark.asyncio
class TestFreezePayoutsIdempotency:
    async def test_same_admin_same_reason_is_pure_noop(self) -> None:
        # arrange: already frozen by admin 42 with reason X.
        admin_id_seed = 1
        existing = PayoutFreeze.frozen(
            admin_id=admin_id_seed,
            at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
            reason="suspicious payouts",
        )
        repo = FakePayoutFreezeRepository(state=existing)
        uc, admins, repo, audit, _uow = _build_freeze(payout_freeze=repo)
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN, admin_id=admin_id_seed)

        out = await uc.execute(
            FreezePayoutsInput(actor_tg_id=42, reason="suspicious payouts"),
        )

        assert out.is_frozen is True
        assert out.was_already_frozen is True
        # State unchanged (same instance, same fields).
        assert repo.state.frozen_at == existing.frozen_at
        assert repo.state.frozen_by_admin_id == existing.frozen_by_admin_id
        assert repo.state.reason == existing.reason
        # No additional set_frozen call.
        assert repo.set_frozen_calls == []
        # No audit entry written.
        assert audit.entries == []

    async def test_same_admin_different_reason_writes_audit(self) -> None:
        # arrange: already frozen by admin 42 with reason X.
        admin_id_seed = 1
        existing = PayoutFreeze.frozen(
            admin_id=admin_id_seed,
            at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
            reason="initial reason",
        )
        repo = FakePayoutFreezeRepository(state=existing)
        uc, admins, repo, audit, _uow = _build_freeze(payout_freeze=repo)
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN, admin_id=admin_id_seed)

        out = await uc.execute(
            FreezePayoutsInput(actor_tg_id=42, reason="escalated abuse"),
        )

        assert out.was_already_frozen is False
        assert repo.state.reason == "escalated abuse"
        assert repo.state.frozen_at == _NOW
        assert len(repo.set_frozen_calls) == 1
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AdminAuditAction.ADMIN_FREEZE_PAYOUTS
        assert entry.before == {
            "is_frozen": True,
            "frozen_by_admin_id": admin_id_seed,
            "reason": "initial reason",
        }
        assert entry.after == {
            "is_frozen": True,
            "frozen_by_admin_id": admin_id_seed,
            "reason": "escalated abuse",
        }

    async def test_different_admin_same_reason_writes_audit(self) -> None:
        existing = PayoutFreeze.frozen(
            admin_id=1,
            at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
            reason="suspicious payouts",
        )
        repo = FakePayoutFreezeRepository(state=existing)
        uc, admins, repo, audit, _uow = _build_freeze(payout_freeze=repo)
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, admin_id=2)

        out = await uc.execute(
            FreezePayoutsInput(actor_tg_id=99, reason="suspicious payouts"),
        )

        assert out.was_already_frozen is False
        assert repo.state.frozen_by_admin_id == 2
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.admin_id == 2
        assert entry.before == {
            "is_frozen": True,
            "frozen_by_admin_id": 1,
            "reason": "suspicious payouts",
        }
        assert entry.after == {
            "is_frozen": True,
            "frozen_by_admin_id": 2,
            "reason": "suspicious payouts",
        }


@pytest.mark.asyncio
class TestUnfreezePayoutsAuthorization:
    async def test_unknown_actor_raises(self) -> None:
        uc, _admins, repo, audit, _uow = _build_unfreeze()

        with pytest.raises(AuthorizationError):
            await uc.execute(UnfreezePayoutsInput(actor_tg_id=99))

        assert audit.entries == []
        assert repo.set_unfrozen_calls == 0

    async def test_inactive_admin_raises(self) -> None:
        uc, admins, repo, audit, _uow = _build_unfreeze()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN, is_active=False)

        with pytest.raises(AuthorizationError):
            await uc.execute(UnfreezePayoutsInput(actor_tg_id=42))

        assert audit.entries == []
        assert repo.set_unfrozen_calls == 0

    async def test_rbac_denied_writes_audit(self) -> None:
        uc, admins, repo, audit, _uow = _build_unfreeze(authz=FakeAdminAuthzDenyAll())
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        with pytest.raises(AdminAuthorizationDeniedError):
            await uc.execute(UnfreezePayoutsInput(actor_tg_id=42, tg_chat_id=-100))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AdminAuditAction.ADMIN_AUTHORIZATION_DENIED
        assert entry.target_kind == "payout_freeze"
        assert entry.target_id == "all"
        assert repo.set_unfrozen_calls == 0


@pytest.mark.asyncio
class TestUnfreezePayoutsHappyPath:
    async def test_unfreezes_state_and_writes_audit(self) -> None:
        existing = PayoutFreeze.frozen(
            admin_id=1,
            at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
            reason="suspicious",
        )
        repo = FakePayoutFreezeRepository(state=existing)
        uc, admins, repo, audit, uow = _build_unfreeze(payout_freeze=repo)
        admin = admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN, admin_id=2)

        out = await uc.execute(
            UnfreezePayoutsInput(
                actor_tg_id=42,
                reason="all clear",
                tg_chat_id=-100,
            ),
        )

        assert out.is_frozen is False
        assert out.was_already_unfrozen is False

        assert repo.state.is_frozen is False
        assert repo.state.frozen_by_admin_id is None
        assert repo.state.frozen_at is None
        assert repo.state.reason is None
        assert repo.set_unfrozen_calls == 1

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AdminAuditAction.ADMIN_UNFREEZE_PAYOUTS
        assert entry.admin_id == admin.id
        assert entry.target_kind == "payout_freeze"
        assert entry.target_id == "all"
        assert entry.before == {
            "is_frozen": True,
            "frozen_by_admin_id": 1,
            "reason": "suspicious",
        }
        assert entry.after == {
            "is_frozen": False,
            "frozen_by_admin_id": None,
            "reason": None,
        }
        assert entry.source is AdminAuditSource.BOT
        assert entry.tg_chat_id == -100
        assert entry.reason == "all clear"
        assert entry.occurred_at == _NOW

        assert uow.commits == 1
        assert uow.rollbacks == 0

    async def test_default_reason_when_none_provided(self) -> None:
        existing = PayoutFreeze.frozen(
            admin_id=1,
            at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
            reason="suspicious",
        )
        repo = FakePayoutFreezeRepository(state=existing)
        uc, admins, _repo, audit, _uow = _build_unfreeze(payout_freeze=repo)
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        out = await uc.execute(UnfreezePayoutsInput(actor_tg_id=42))

        assert out.was_already_unfrozen is False
        assert len(audit.entries) == 1
        assert audit.entries[0].reason == "unfreeze payouts"


@pytest.mark.asyncio
class TestUnfreezePayoutsIdempotency:
    async def test_already_unfrozen_is_pure_noop(self) -> None:
        # State on a fresh repo defaults to PayoutFreeze.unfrozen().
        uc, admins, repo, audit, _uow = _build_unfreeze()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        out = await uc.execute(
            UnfreezePayoutsInput(actor_tg_id=42, reason="redundant unfreeze"),
        )

        assert out.is_frozen is False
        assert out.was_already_unfrozen is True
        assert repo.set_unfrozen_calls == 0
        assert audit.entries == []
