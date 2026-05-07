"""Unit-тесты `BroadcastAnnouncement` — фаза 1 `/announce` (Спринт 2.5-D.4)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin import (
    BROADCAST_MESSAGE_MAX_LEN,
    BroadcastAnnouncement,
    BroadcastAnnouncementInput,
    BroadcastLocaleFilter,
    BroadcastLocaleFilterInvalidError,
    BroadcastMessageEmptyError,
    BroadcastMessageTooLongError,
    parse_locale_filter,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuthorizationDeniedError,
    AdminRole,
)
from pipirik_wars.domain.player import Player, PlayerStatus, Username
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll, FakeAdminAuthzDenyAll
from tests.fakes.admin_repo import FakeAdminRepository
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


def _build_use_case(
    *,
    authz: FakeAdminAuthzAllowAll | FakeAdminAuthzDenyAll | None = None,
) -> tuple[
    BroadcastAnnouncement,
    FakeAdminRepository,
    FakePlayerRepository,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    players = FakePlayerRepository()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    return (
        BroadcastAnnouncement(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=authz or FakeAdminAuthzAllowAll(),
        ),
        admins,
        players,
        audit,
        uow,
    )


@pytest.mark.asyncio
class TestBroadcastAnnouncementValidation:
    async def test_invalid_locale_filter_raises(self) -> None:
        uc, admins, _p, audit, _uow = _build_use_case()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        with pytest.raises(BroadcastLocaleFilterInvalidError):
            await uc.execute(
                BroadcastAnnouncementInput(
                    actor_tg_id=42,
                    locale_filter_raw="de",
                    message_raw="hello",
                ),
            )

        # Validation падает до RBAC — admin-аудит не пишется.
        assert audit.entries == []

    async def test_empty_message_raises(self) -> None:
        uc, admins, _p, _a, _uow = _build_use_case()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        with pytest.raises(BroadcastMessageEmptyError):
            await uc.execute(
                BroadcastAnnouncementInput(
                    actor_tg_id=42,
                    locale_filter_raw="ru",
                    message_raw="   ",
                ),
            )

    async def test_message_too_long_raises(self) -> None:
        uc, admins, _p, _a, _uow = _build_use_case()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        with pytest.raises(BroadcastMessageTooLongError):
            await uc.execute(
                BroadcastAnnouncementInput(
                    actor_tg_id=42,
                    locale_filter_raw="*",
                    message_raw="A" * (BROADCAST_MESSAGE_MAX_LEN + 1),
                ),
            )


@pytest.mark.asyncio
class TestBroadcastAnnouncementAuthorization:
    async def test_inactive_admin_raises(self) -> None:
        uc, admins, _p, audit, _uow = _build_use_case()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN, is_active=False)

        with pytest.raises(AuthorizationError):
            await uc.execute(
                BroadcastAnnouncementInput(
                    actor_tg_id=42,
                    locale_filter_raw="ru",
                    message_raw="hi",
                ),
            )

        assert audit.entries == []

    async def test_unknown_actor_raises(self) -> None:
        uc, _admins, _p, audit, _uow = _build_use_case()

        with pytest.raises(AuthorizationError):
            await uc.execute(
                BroadcastAnnouncementInput(
                    actor_tg_id=99,
                    locale_filter_raw="ru",
                    message_raw="hi",
                ),
            )

        assert audit.entries == []

    async def test_rbac_denied_writes_audit(self) -> None:
        uc, admins, _p, audit, _uow = _build_use_case(authz=FakeAdminAuthzDenyAll())
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        with pytest.raises(AdminAuthorizationDeniedError):
            await uc.execute(
                BroadcastAnnouncementInput(
                    actor_tg_id=42,
                    locale_filter_raw="ru",
                    message_raw="hi",
                    tg_chat_id=-100,
                ),
            )

        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.action == AdminAuditAction.ADMIN_AUTHORIZATION_DENIED
        assert a.target_kind == "locale_filter"
        assert a.target_id == "ru"
        assert a.tg_chat_id == -100


@pytest.mark.asyncio
class TestBroadcastAnnouncementHappyPath:
    async def test_ru_filter_counts_only_ru(self) -> None:
        uc, admins, players, audit, _uow = _build_use_case()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        _seed_player(players, tg_id=100, locale_override="ru")
        _seed_player(players, tg_id=101, locale_override="en")
        _seed_player(players, tg_id=102, locale_override=None)
        _seed_player(players, tg_id=103, locale_override="ru", status=PlayerStatus.FROZEN)

        out = await uc.execute(
            BroadcastAnnouncementInput(
                actor_tg_id=42,
                locale_filter_raw="ru",
                message_raw="привет",
            ),
        )

        assert out.locale_filter is BroadcastLocaleFilter.RU
        assert out.message == "привет"
        # Только активный RU-игрок попадает; FROZEN-игрок исключён.
        assert out.recipient_count == 1
        # Happy-path не пишет audit (write-side audit идёт в фазе 2).
        assert audit.entries == []

    async def test_en_filter_includes_null_locale(self) -> None:
        uc, admins, players, _a, _uow = _build_use_case()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        _seed_player(players, tg_id=100, locale_override="en")
        _seed_player(players, tg_id=101, locale_override=None)
        _seed_player(players, tg_id=102, locale_override="ru")

        out = await uc.execute(
            BroadcastAnnouncementInput(
                actor_tg_id=42,
                locale_filter_raw="en",
                message_raw="hello",
            ),
        )

        # `en`-локаль + `NULL` (DEFAULT_LOCALE = en) → 2 адресата.
        assert out.recipient_count == 2

    async def test_all_filter_with_star_alias(self) -> None:
        uc, admins, players, _a, _uow = _build_use_case()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        _seed_player(players, tg_id=100, locale_override="en")
        _seed_player(players, tg_id=101, locale_override=None)
        _seed_player(players, tg_id=102, locale_override="ru")
        _seed_player(players, tg_id=103, locale_override="ru", status=PlayerStatus.BANNED)

        out = await uc.execute(
            BroadcastAnnouncementInput(
                actor_tg_id=42,
                locale_filter_raw="*",
                message_raw="anyone there?",
            ),
        )

        assert out.locale_filter is BroadcastLocaleFilter.ALL
        # ALL включает ACTIVE-игроков всех локалей; BANNED исключается.
        assert out.recipient_count == 3

    async def test_message_normalization_strips_whitespace(self) -> None:
        uc, admins, players, _a, _uow = _build_use_case()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        _seed_player(players, tg_id=100, locale_override="ru")

        out = await uc.execute(
            BroadcastAnnouncementInput(
                actor_tg_id=42,
                locale_filter_raw="  RU  ",
                message_raw="\n\n  привет!  \n",
            ),
        )

        assert out.locale_filter is BroadcastLocaleFilter.RU
        assert out.message == "привет!"


class TestParseLocaleFilter:
    def test_ru(self) -> None:
        assert parse_locale_filter("ru") is BroadcastLocaleFilter.RU
        assert parse_locale_filter("RU") is BroadcastLocaleFilter.RU

    def test_star_is_all(self) -> None:
        assert parse_locale_filter("*") is BroadcastLocaleFilter.ALL

    def test_invalid_value(self) -> None:
        with pytest.raises(BroadcastLocaleFilterInvalidError):
            parse_locale_filter("fr")
