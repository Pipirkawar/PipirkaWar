"""Unit-тесты VO `AdminConfirmRequest`/`AdminConfirmEntry` (Спринт 2.5-A.3)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from pipirik_wars.domain.admin import (
    AdminConfirmEntry,
    AdminConfirmError,
    AdminConfirmRequest,
    ConfirmAdminMismatchError,
    ConfirmCodeInvalidError,
    ConfirmTokenExpiredError,
    ConfirmTokenNotFoundError,
    TotpNotConfiguredError,
)
from pipirik_wars.shared.errors import DomainError


class TestAdminConfirmRequest:
    def test_default_payload_is_empty_mapping(self) -> None:
        req = AdminConfirmRequest(
            admin_id=1,
            command_kind="ban",
            target_kind="player",
            target_id="42",
        )
        assert req.payload == MappingProxyType({})

    def test_immutable(self) -> None:
        req = AdminConfirmRequest(
            admin_id=1,
            command_kind="ban",
            target_kind="player",
            target_id="42",
        )
        with pytest.raises(FrozenInstanceError):
            req.admin_id = 2

    def test_payload_round_trip(self) -> None:
        req = AdminConfirmRequest(
            admin_id=1,
            command_kind="grant_length",
            target_kind="player",
            target_id="42",
            payload={"cm": 5, "reason": "compensation"},
        )
        assert req.payload["cm"] == 5
        assert req.payload["reason"] == "compensation"


class TestAdminConfirmEntry:
    def test_immutable(self) -> None:
        entry = AdminConfirmEntry(
            request=AdminConfirmRequest(
                admin_id=1,
                command_kind="ban",
                target_kind="player",
                target_id="42",
            ),
            expires_at=datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC),
        )
        with pytest.raises(FrozenInstanceError):
            entry.expires_at = datetime.now(UTC)


class TestErrorHierarchy:
    @pytest.mark.parametrize(
        "exc_class",
        [
            ConfirmTokenNotFoundError,
            ConfirmTokenExpiredError,
            ConfirmCodeInvalidError,
            ConfirmAdminMismatchError,
            TotpNotConfiguredError,
        ],
    )
    def test_all_subclass_admin_confirm_error(self, exc_class: type[AdminConfirmError]) -> None:
        assert issubclass(exc_class, AdminConfirmError)
        assert issubclass(exc_class, DomainError)
