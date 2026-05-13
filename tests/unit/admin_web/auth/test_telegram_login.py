"""Unit-тесты Telegram Login Widget HMAC-верификации (Sprint 4.5-A)."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from pipirik_wars.admin_web.auth.telegram_login import (
    InvalidLoginHashError,
    StaleLoginError,
    TelegramLoginData,
    verify_telegram_login,
)

BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"


def _sign(data: dict[str, object], token: str = BOT_TOKEN) -> str:
    check_pairs = [f"{k}={data[k]}" for k in sorted(data) if k != "hash"]
    check_string = "\n".join(check_pairs)
    secret = hashlib.sha256(token.encode()).digest()
    return hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()


def _make_data(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": 12345,
        "first_name": "John",
        "auth_date": int(time.time()),
    }
    base.update(overrides)
    base["hash"] = _sign(base)
    return base


class TestVerifyTelegramLogin:
    def test_valid_data(self) -> None:
        data = _make_data(username="john_doe")
        result = verify_telegram_login(data=data, bot_token=BOT_TOKEN)
        assert isinstance(result, TelegramLoginData)
        assert result.id == 12345
        assert result.first_name == "John"
        assert result.username == "john_doe"

    def test_all_optional_fields(self) -> None:
        data = _make_data(
            username="tester",
            last_name="Doe",
            photo_url="https://t.me/photo.jpg",
        )
        result = verify_telegram_login(data=data, bot_token=BOT_TOKEN)
        assert result.last_name == "Doe"
        assert result.photo_url == "https://t.me/photo.jpg"

    def test_missing_optional_fields(self) -> None:
        data = _make_data()
        result = verify_telegram_login(data=data, bot_token=BOT_TOKEN)
        assert result.last_name is None
        assert result.username is None
        assert result.photo_url is None

    def test_invalid_hash_raises(self) -> None:
        data = _make_data()
        data["hash"] = "deadbeef" * 8
        with pytest.raises(InvalidLoginHashError):
            verify_telegram_login(data=data, bot_token=BOT_TOKEN)

    def test_wrong_token_raises(self) -> None:
        data = _make_data()
        with pytest.raises(InvalidLoginHashError):
            verify_telegram_login(data=data, bot_token="wrong:token")

    def test_stale_auth_date_raises(self) -> None:
        data = _make_data(auth_date=int(time.time()) - 100000)
        data["hash"] = _sign(data)
        with pytest.raises(StaleLoginError):
            verify_telegram_login(data=data, bot_token=BOT_TOKEN)

    def test_custom_max_age(self) -> None:
        data = _make_data(auth_date=int(time.time()) - 10)
        data["hash"] = _sign(data)
        with pytest.raises(StaleLoginError):
            verify_telegram_login(data=data, bot_token=BOT_TOKEN, max_age_seconds=5)

    def test_empty_bot_token_raises(self) -> None:
        data = _make_data()
        with pytest.raises(ValueError, match="bot_token must not be empty"):
            verify_telegram_login(data=data, bot_token="")

    def test_tampered_field_raises(self) -> None:
        data = _make_data()
        data["first_name"] = "Tampered"
        with pytest.raises(InvalidLoginHashError):
            verify_telegram_login(data=data, bot_token=BOT_TOKEN)
