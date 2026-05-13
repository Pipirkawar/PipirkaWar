"""Unit-тесты AdminWebSettings (Sprint 4.5-A)."""

from __future__ import annotations

import os
from unittest import mock

import pytest
from pydantic import ValidationError

from pipirik_wars.admin_web.settings import AdminWebSettings

_REQUIRED_ENV = {
    "ADMIN_WEB_SECRET_KEY": "a" * 32,
    "ADMIN_WEB_BOT_USERNAME": "testbot",
    "ADMIN_WEB_BOT_TOKEN": "123:abc",
}


class TestAdminWebSettings:
    def test_defaults(self) -> None:
        with mock.patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = AdminWebSettings()  # type: ignore[call-arg]
        assert s.host == "127.0.0.1"
        assert s.port == 8080
        assert s.secret_key.get_secret_value() == "a" * 32
        assert s.allowed_ips == ""
        assert s.trust_proxy is False
        assert s.session_max_age_seconds == 3600
        assert s.totp_verify_ttl_seconds == 14400
        assert s.cookie_insecure_dev is False
        assert s.bootstrap_admin_password is None

    def test_custom_values(self) -> None:
        env = {
            **_REQUIRED_ENV,
            "ADMIN_WEB_HOST": "0.0.0.0",
            "ADMIN_WEB_PORT": "9999",
            "ADMIN_WEB_ALLOWED_IPS": "10.0.0.0/8",
            "ADMIN_WEB_TRUST_PROXY": "true",
            "ADMIN_WEB_SESSION_MAX_AGE_SECONDS": "7200",
            "ADMIN_WEB_TOTP_VERIFY_TTL_SECONDS": "1800",
            "ADMIN_WEB_COOKIE_INSECURE_DEV": "true",
            "ADMIN_WEB_BOOTSTRAP_ADMIN_PASSWORD": "hunter2",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            s = AdminWebSettings()  # type: ignore[call-arg]
        assert s.host == "0.0.0.0"
        assert s.port == 9999
        assert s.allowed_ips == "10.0.0.0/8"
        assert s.trust_proxy is True
        assert s.session_max_age_seconds == 7200
        assert s.totp_verify_ttl_seconds == 1800
        assert s.cookie_insecure_dev is True
        assert s.bootstrap_admin_password == "hunter2"

    def test_secret_key_required(self) -> None:
        env = {
            "ADMIN_WEB_BOT_USERNAME": "testbot",
            "ADMIN_WEB_BOT_TOKEN": "123:abc",
        }
        with mock.patch.dict(os.environ, env, clear=True), pytest.raises(ValidationError):
            AdminWebSettings()  # type: ignore[call-arg]

    def test_bot_username_required(self) -> None:
        env = {
            "ADMIN_WEB_SECRET_KEY": "a" * 32,
            "ADMIN_WEB_BOT_TOKEN": "123:abc",
        }
        with mock.patch.dict(os.environ, env, clear=True), pytest.raises(ValidationError):
            AdminWebSettings()  # type: ignore[call-arg]
