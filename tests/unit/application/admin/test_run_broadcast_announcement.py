"""Unit-тесты `RunBroadcastAnnouncement` — фаза 2 `/announce` (Спринт 2.5-D.4)."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin import (
    BROADCAST_AUDIT_MESSAGE_PREVIEW_LEN,
    BroadcastLocaleFilter,
    RunBroadcastAnnouncement,
    RunBroadcastAnnouncementInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditSource,
    AdminAuthorizationDeniedError,
    AdminRole,
)
from pipirik_wars.domain.player import Player, PlayerStatus, Username
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll, FakeAdminAuthzDenyAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.broadcast import FakeBroadcastSender
from tests.fakes.clock import FakeClock
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.uow import FakeUnitOfWork

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    locale_override: str | None,
    status: PlayerStatus = PlayerStatus.ACTIVE,
) -> Player:
    new_id = (max((p.id or 0 for p in players.rows), default=0)) + 1
    base = Player.new(tg_id=tg_id, username=Username(value=f"u{tg_id}"), now=_NOW)
    seeded = replace(base, id=new_id, status=status, locale_override=locale_override)
    players.rows.append(seeded)
    return seeded


class _RecordingSleep:
    """Проксирует sleep, фиксируя длительности и не блокируя тест."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _build_use_case(
    *,
    sender: FakeBroadcastSender | None = None,
    sleep: _RecordingSleep | None = None,
    batch_size: int = 25,
    batch_interval_seconds: float = 1.0,
    authz: FakeAdminAuthzAllowAll | FakeAdminAuthzDenyAll | None = None,
) -> tuple[
    RunBroadcastAnnouncement,
    FakeAdminRepository,
    FakePlayerRepository,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
    FakeBroadcastSender,
    _RecordingSleep,
]:
    admins = FakeAdminRepository()
    players = FakePlayerRepository()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    sender = sender or FakeBroadcastSender()
    sleep = sleep or _RecordingSleep()

    async def sleep_proxy(seconds: float) -> None:
        await sleep(seconds)

    return (
        RunBroadcastAnnouncement(
            uow=uow,
            admins=admins,
            players=players,
            sender=sender,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=authz or FakeAdminAuthzAllowAll(),
            sleep=sleep_proxy,
            batch_size=batch_size,
            batch_interval_seconds=batch_interval_seconds,
        ),
        admins,
        players,
        audit,
        uow,
        sender,
        sleep,
    )


@pytest.mark.asyncio
class TestRunBroadcastAnnouncementAuthorization:
    async def test_inactive_admin_raises(self) -> None:
        uc, admins, _p, audit, _uow, _s, _sleep = _build_use_case()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN, is_active=False)

        with pytest.raises(AuthorizationError):
            await uc.execute(
                RunBroadcastAnnouncementInput(
                    actor_tg_id=42,
                    locale_filter=BroadcastLocaleFilter.RU,
                    message="hi",
                ),
            )

        # Без active-admin даже AUTHORIZATION_DENIED не пишется.
        assert audit.entries == []

    async def test_rbac_denied_writes_audit_no_send(self) -> None:
        uc, admins, players, audit, _uow, sender, _sleep = _build_use_case(
            authz=FakeAdminAuthzDenyAll(),
        )
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100, locale_override="ru")

        with pytest.raises(AdminAuthorizationDeniedError):
            await uc.execute(
                RunBroadcastAnnouncementInput(
                    actor_tg_id=42,
                    locale_filter=BroadcastLocaleFilter.RU,
                    message="hi",
                    tg_chat_id=-100,
                ),
            )

        # Только AUTHORIZATION_DENIED, без BROADCAST_SENT.
        assert len(audit.entries) == 1
        assert audit.entries[0].action == AdminAuditAction.ADMIN_AUTHORIZATION_DENIED
        assert sender.sent_log == []


@pytest.mark.asyncio
class TestRunBroadcastAnnouncementHappyPath:
    async def test_single_batch_no_sleep(self) -> None:
        sender = FakeBroadcastSender(default_result="sent")
        uc, admins, players, audit, _uow, _s, sleep = _build_use_case(
            sender=sender,
            batch_size=10,
            batch_interval_seconds=1.0,
        )
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        for tg in range(100, 105):
            _seed_player(players, tg_id=tg, locale_override="ru")

        out = await uc.execute(
            RunBroadcastAnnouncementInput(
                actor_tg_id=42,
                locale_filter=BroadcastLocaleFilter.RU,
                message="hello!",
            ),
        )

        assert out.recipient_count == 5
        assert out.sent_count == 5
        assert out.failed_count == 0
        assert out.blocked_count == 0
        # 5 игроков влезли в один батч (size=10) — sleep не вызывался.
        assert sleep.calls == []
        # Все 5 адресатов получили сообщение.
        assert {entry[0] for entry in sender.sent_log} == {100, 101, 102, 103, 104}
        assert all(entry[1] == "hello!" for entry in sender.sent_log)

    async def test_multiple_batches_sleeps_between(self) -> None:
        sender = FakeBroadcastSender(default_result="sent")
        uc, admins, players, _audit, _uow, _s, sleep = _build_use_case(
            sender=sender,
            batch_size=2,
            batch_interval_seconds=0.5,
        )
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        for tg in range(100, 105):
            _seed_player(players, tg_id=tg, locale_override="ru")

        await uc.execute(
            RunBroadcastAnnouncementInput(
                actor_tg_id=42,
                locale_filter=BroadcastLocaleFilter.RU,
                message="hello!",
            ),
        )

        # 5 адресатов, batch_size=2 → батчей 3 → sleep вызывается 2 раза
        # (между 1↔2 и 2↔3); перед первым батчем не ждём.
        assert sleep.calls == [0.5, 0.5]

    async def test_mixed_send_results_aggregated(self) -> None:
        sender = FakeBroadcastSender(
            results_by_tg_id={
                100: "sent",
                101: "failed",
                102: "blocked",
                103: "sent",
            },
        )
        uc, admins, players, audit, _uow, _s, _sleep = _build_use_case(sender=sender)
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        for tg in range(100, 104):
            _seed_player(players, tg_id=tg, locale_override="ru")

        out = await uc.execute(
            RunBroadcastAnnouncementInput(
                actor_tg_id=42,
                locale_filter=BroadcastLocaleFilter.RU,
                message="hi",
                tg_chat_id=-100,
            ),
        )

        assert out.sent_count == 2
        assert out.failed_count == 1
        assert out.blocked_count == 1
        # Audit-запись о результате.
        broadcast_entries = [
            e for e in audit.entries if e.action == AdminAuditAction.ADMIN_BROADCAST_SENT
        ]
        assert len(broadcast_entries) == 1
        a = broadcast_entries[0]
        assert a.target_kind == "locale_filter"
        assert a.target_id == "ru"
        assert a.before == {"recipient_count": 4}
        assert a.after is not None
        assert a.after["sent_count"] == 2
        assert a.after["failed_count"] == 1
        assert a.after["blocked_count"] == 1
        assert a.after["message_preview"] == "hi"
        assert a.source == AdminAuditSource.BOT
        assert a.tg_chat_id == -100

    async def test_audit_message_preview_truncated(self) -> None:
        long_message = "А" * (BROADCAST_AUDIT_MESSAGE_PREVIEW_LEN + 50)
        uc, admins, players, audit, _uow, _s, _sleep = _build_use_case()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        _seed_player(players, tg_id=100, locale_override="ru")

        await uc.execute(
            RunBroadcastAnnouncementInput(
                actor_tg_id=42,
                locale_filter=BroadcastLocaleFilter.RU,
                message=long_message,
            ),
        )

        broadcast_entries = [
            e for e in audit.entries if e.action == AdminAuditAction.ADMIN_BROADCAST_SENT
        ]
        after = broadcast_entries[0].after
        assert after is not None
        preview = after["message_preview"]
        # Превью длиной ровно `BROADCAST_AUDIT_MESSAGE_PREVIEW_LEN`,
        # последний символ — `…` (троеточие — индикатор обрезания).
        assert isinstance(preview, str)
        assert len(preview) == BROADCAST_AUDIT_MESSAGE_PREVIEW_LEN
        assert preview.endswith("…")

    async def test_empty_recipient_list_writes_zero_audit(self) -> None:
        uc, admins, _players, audit, _uow, sender, sleep = _build_use_case()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        # Адресатов нет.

        out = await uc.execute(
            RunBroadcastAnnouncementInput(
                actor_tg_id=42,
                locale_filter=BroadcastLocaleFilter.RU,
                message="hi",
            ),
        )

        assert out.recipient_count == 0
        assert out.sent_count == 0
        assert sender.sent_log == []
        assert sleep.calls == []
        broadcast_entries = [
            e for e in audit.entries if e.action == AdminAuditAction.ADMIN_BROADCAST_SENT
        ]
        # Аудит всё равно пишется — super-admin должен видеть, что
        # рассылка состоялась с нулём адресатов (например, опечатался в
        # фильтре локали и попал на пустую выборку).
        assert len(broadcast_entries) == 1
        a = broadcast_entries[0]
        assert a.before == {"recipient_count": 0}
        assert a.after is not None
        assert a.after["sent_count"] == 0


class TestRunBroadcastAnnouncementValidation:
    def test_negative_batch_size_rejected(self) -> None:
        async def _noop(_seconds: float) -> None:
            return None

        with pytest.raises(ValueError, match="batch_size"):
            RunBroadcastAnnouncement(
                uow=FakeUnitOfWork(),
                admins=FakeAdminRepository(),
                players=FakePlayerRepository(),
                sender=FakeBroadcastSender(),
                audit=FakeAdminAuditLogger(),
                clock=FakeClock(_NOW),
                authz=FakeAdminAuthzAllowAll(),
                sleep=_noop,
                batch_size=0,
            )

    def test_negative_interval_rejected(self) -> None:
        async def _noop(_seconds: float) -> None:
            return None

        with pytest.raises(ValueError, match="batch_interval_seconds"):
            RunBroadcastAnnouncement(
                uow=FakeUnitOfWork(),
                admins=FakeAdminRepository(),
                players=FakePlayerRepository(),
                sender=FakeBroadcastSender(),
                audit=FakeAdminAuditLogger(),
                clock=FakeClock(_NOW),
                authz=FakeAdminAuthzAllowAll(),
                sleep=_noop,
                batch_interval_seconds=-0.1,
            )


def _coro_proxy(coro: Awaitable[None]) -> Awaitable[None]:
    """Утилита, чтобы mypy не ругался при передаче coro в spawner."""
    return coro
