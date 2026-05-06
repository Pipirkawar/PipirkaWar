"""Unit-тесты `VerifyAdminConfirm` (Спринт 2.5-A.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.admin import (
    VerifyAdminConfirm,
    VerifyAdminConfirmInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminConfirmEntry,
    AdminConfirmRequest,
    AdminRole,
    ConfirmAdminMismatchError,
    ConfirmCodeInvalidError,
    ConfirmTokenExpiredError,
    ConfirmTokenNotFoundError,
    ITotpVerifier,
    TotpNotConfiguredError,
)
from pipirik_wars.infrastructure.admin.in_memory_confirm_store import (
    InMemoryAdminConfirmStore,
)
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clock import FakeClock
from tests.fakes.uow import FakeUnitOfWork

_FIXED_NOW = datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)


class _StubTotpVerifier(ITotpVerifier):
    """Стаб-верификатор: всегда возвращает заранее заданный bool, считает вызовы."""

    __slots__ = ("calls", "result")

    def __init__(self, *, result: bool) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def verify(self, *, secret: str, code: str) -> bool:
        self.calls.append((secret, code))
        return self.result


def _build(
    *,
    totp_result: bool = True,
) -> tuple[
    VerifyAdminConfirm,
    FakeAdminRepository,
    InMemoryAdminConfirmStore,
    _StubTotpVerifier,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
    FakeClock,
]:
    admins = FakeAdminRepository()
    store = InMemoryAdminConfirmStore()
    totp = _StubTotpVerifier(result=totp_result)
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    clock = FakeClock(_FIXED_NOW)
    use_case = VerifyAdminConfirm(
        uow=uow,
        admins=admins,
        store=store,
        totp=totp,
        audit=audit,
        clock=clock,
    )
    return use_case, admins, store, totp, audit, uow, clock


async def _seed_token(
    *,
    store: InMemoryAdminConfirmStore,
    admin_id: int,
    token: str = "tok-abc",
    expires_at: datetime = _FIXED_NOW + timedelta(seconds=60),
    payload: dict[str, object] | None = None,
) -> None:
    await store.save(
        token=token,
        entry=AdminConfirmEntry(
            request=AdminConfirmRequest(
                admin_id=admin_id,
                command_kind="ban",
                target_kind="player",
                target_id="100500",
                payload=payload or {"reason": "spam"},
            ),
            expires_at=expires_at,
        ),
    )


@pytest.mark.asyncio
class TestVerifyAdminConfirm:
    async def test_unknown_admin_raises_authorization_error(self) -> None:
        use_case, _admins, _store, totp, audit, uow, _ = _build()
        with pytest.raises(AuthorizationError):
            await use_case.execute(
                VerifyAdminConfirmInput(
                    actor_tg_id=999,
                    token="tok-abc",
                    code="123456",
                ),
            )
        assert totp.calls == []
        assert audit.entries == []
        assert uow.commits == 0

    async def test_inactive_admin_raises_authorization_error(self) -> None:
        use_case, admins, _store, _totp, _audit, _uow, _ = _build()
        admins.seed(
            tg_id=42,
            role=AdminRole.SUPER_ADMIN,
            is_active=False,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        with pytest.raises(AuthorizationError):
            await use_case.execute(
                VerifyAdminConfirmInput(
                    actor_tg_id=42,
                    token="tok-abc",
                    code="123456",
                ),
            )

    async def test_admin_without_totp_raises_not_configured(self) -> None:
        use_case, admins, _store, _totp, _audit, _uow, _ = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN, totp_secret=None)
        with pytest.raises(TotpNotConfiguredError):
            await use_case.execute(
                VerifyAdminConfirmInput(
                    actor_tg_id=42,
                    token="tok-abc",
                    code="123456",
                ),
            )

    async def test_unknown_token_raises_not_found(self) -> None:
        use_case, admins, _store, totp, audit, uow, _ = _build()
        admins.seed(
            tg_id=42,
            role=AdminRole.SUPER_ADMIN,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        with pytest.raises(ConfirmTokenNotFoundError):
            await use_case.execute(
                VerifyAdminConfirmInput(
                    actor_tg_id=42,
                    token="missing",
                    code="123456",
                ),
            )
        # Никакой audit-записи: токен даже не существовал, нечего «светить».
        assert audit.entries == []
        assert uow.commits == 0
        assert totp.calls == []

    async def test_admin_mismatch_raises_and_audits(self) -> None:
        use_case, admins, store, totp, audit, uow, _ = _build()
        owner = admins.seed(
            tg_id=42,
            role=AdminRole.SUPER_ADMIN,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        intruder = admins.seed(
            tg_id=43,
            role=AdminRole.SUPPORT,
            totp_secret="ABCDEFGHIJKLMNOP",
        )
        assert owner.id is not None
        assert intruder.id is not None

        await _seed_token(store=store, admin_id=owner.id)

        with pytest.raises(ConfirmAdminMismatchError):
            await use_case.execute(
                VerifyAdminConfirmInput(
                    actor_tg_id=43,
                    token="tok-abc",
                    code="123456",
                ),
            )
        # Токен сожжён (одноразовый), TOTP не вызывался.
        assert await store.pop(token="tok-abc") is None
        assert totp.calls == []
        # Audit-запись о провале с raison admin_mismatch.
        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.action == AdminAuditAction.ADMIN_CONFIRM_FAILED
        assert a.admin_id == intruder.id
        assert a.reason.startswith("confirm_failed:ban:admin_mismatch")
        assert uow.commits == 1

    async def test_expired_token_raises_and_audits(self) -> None:
        use_case, admins, store, totp, audit, uow, _ = _build()
        admin = admins.seed(
            tg_id=42,
            role=AdminRole.SUPER_ADMIN,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        assert admin.id is not None
        await _seed_token(
            store=store,
            admin_id=admin.id,
            expires_at=_FIXED_NOW - timedelta(seconds=1),
        )

        with pytest.raises(ConfirmTokenExpiredError):
            await use_case.execute(
                VerifyAdminConfirmInput(
                    actor_tg_id=42,
                    token="tok-abc",
                    code="123456",
                ),
            )
        assert totp.calls == []
        assert len(audit.entries) == 1
        assert audit.entries[0].action == AdminAuditAction.ADMIN_CONFIRM_FAILED
        assert audit.entries[0].reason.endswith("token_expired")
        assert uow.commits == 1

    async def test_invalid_code_raises_and_audits(self) -> None:
        use_case, admins, store, totp, audit, uow, _ = _build(totp_result=False)
        admin = admins.seed(
            tg_id=42,
            role=AdminRole.SUPER_ADMIN,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        assert admin.id is not None
        await _seed_token(store=store, admin_id=admin.id)

        with pytest.raises(ConfirmCodeInvalidError):
            await use_case.execute(
                VerifyAdminConfirmInput(
                    actor_tg_id=42,
                    token="tok-abc",
                    code="111111",
                ),
            )
        # TOTP-верификатор был вызван, но вернул False.
        assert totp.calls == [("JBSWY3DPEHPK3PXP", "111111")]
        # Audit-запись о провале.
        assert len(audit.entries) == 1
        assert audit.entries[0].action == AdminAuditAction.ADMIN_CONFIRM_FAILED
        assert audit.entries[0].reason.endswith("code_invalid")
        # Токен сожжён.
        assert await store.pop(token="tok-abc") is None

    async def test_valid_code_returns_payload_and_audits_success(self) -> None:
        use_case, admins, store, totp, audit, uow, _ = _build(totp_result=True)
        admin = admins.seed(
            tg_id=42,
            role=AdminRole.SUPER_ADMIN,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        assert admin.id is not None
        await _seed_token(
            store=store,
            admin_id=admin.id,
            payload={"reason": "spam", "duration_days": 7},
        )

        result = await use_case.execute(
            VerifyAdminConfirmInput(
                actor_tg_id=42,
                token="tok-abc",
                code="999999",
                tg_chat_id=-100,
            ),
        )
        assert result.command_kind == "ban"
        assert result.target_kind == "player"
        assert result.target_id == "100500"
        assert result.payload["reason"] == "spam"
        assert result.payload["duration_days"] == 7

        # TOTP вызван 1 раз с правильным секретом.
        assert totp.calls == [("JBSWY3DPEHPK3PXP", "999999")]
        # Audit-запись об успехе.
        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.action == AdminAuditAction.ADMIN_CONFIRM_VERIFIED
        assert a.admin_id == admin.id
        assert a.target_id == "100500"
        assert a.tg_chat_id == -100
        assert a.idempotency_key == "tok-abc"
        # Токен сожжён.
        assert await store.pop(token="tok-abc") is None
        # Транзакция UoW зафиксирована один раз.
        assert uow.commits == 1
        assert uow.rollbacks == 0

    async def test_token_burned_even_on_admin_mismatch(self) -> None:
        """Защита от brute-force-а: токен попадает в store до проверок."""
        use_case, admins, store, _totp, _audit, _uow, _ = _build()
        owner = admins.seed(
            tg_id=42,
            role=AdminRole.SUPER_ADMIN,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        admins.seed(
            tg_id=43,
            role=AdminRole.SUPPORT,
            totp_secret="ABCDEFGHIJKLMNOP",
        )
        assert owner.id is not None
        await _seed_token(store=store, admin_id=owner.id)

        with pytest.raises(ConfirmAdminMismatchError):
            await use_case.execute(
                VerifyAdminConfirmInput(
                    actor_tg_id=43,
                    token="tok-abc",
                    code="123456",
                ),
            )
        # Повторный verify тем же owner-ом — токена уже нет.
        with pytest.raises(ConfirmTokenNotFoundError):
            await use_case.execute(
                VerifyAdminConfirmInput(
                    actor_tg_id=42,
                    token="tok-abc",
                    code="123456",
                ),
            )
