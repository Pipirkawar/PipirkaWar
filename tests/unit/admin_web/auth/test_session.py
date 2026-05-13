"""Unit-тесты signed-cookie session management (Sprint 4.5-A)."""

from __future__ import annotations

import time

import pytest
from itsdangerous import BadSignature

from pipirik_wars.admin_web.auth.session import AdminSession, SessionManager


@pytest.fixture()
def mgr() -> SessionManager:
    return SessionManager(secret_key="test-secret-key-xyz", max_age=3600)


class TestAdminSession:
    def test_to_dict_round_trip(self) -> None:
        session = AdminSession(
            admin_id=42,
            tg_username="alice",
            totp_verified_at=1234567890.5,
            csrf_token="tok123",
        )
        data = session.to_dict()
        restored = AdminSession.from_dict(data)
        assert restored.admin_id == 42
        assert restored.tg_username == "alice"
        assert restored.totp_verified_at == 1234567890.5
        assert restored.csrf_token == "tok123"

    def test_from_dict_none_optionals(self) -> None:
        session = AdminSession(
            admin_id=1,
            tg_username=None,
            totp_verified_at=None,
            csrf_token="abc",
        )
        data = session.to_dict()
        restored = AdminSession.from_dict(data)
        assert restored.tg_username is None
        assert restored.totp_verified_at is None


class TestSessionManager:
    def test_encode_decode_round_trip(self, mgr: SessionManager) -> None:
        session = AdminSession(
            admin_id=99,
            tg_username="bob",
            totp_verified_at=time.time(),
            csrf_token="csrf_test",
        )
        cookie = mgr.encode(session)
        decoded = mgr.decode(cookie)
        assert decoded.admin_id == 99
        assert decoded.tg_username == "bob"
        assert decoded.csrf_token == "csrf_test"

    def test_tampered_cookie_raises(self, mgr: SessionManager) -> None:
        session = AdminSession(
            admin_id=1,
            tg_username=None,
            totp_verified_at=None,
            csrf_token="x",
        )
        cookie = mgr.encode(session)
        tampered = cookie[:-5] + "XXXXX"
        with pytest.raises(BadSignature):
            mgr.decode(tampered)

    def test_different_key_cannot_decode(self) -> None:
        mgr1 = SessionManager(secret_key="key-one", max_age=3600)
        mgr2 = SessionManager(secret_key="key-two", max_age=3600)
        session = AdminSession(
            admin_id=1,
            tg_username=None,
            totp_verified_at=None,
            csrf_token="x",
        )
        cookie = mgr1.encode(session)
        with pytest.raises(BadSignature):
            mgr2.decode(cookie)
