"""Unit-тесты pydantic-settings."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from pipirik_wars.infrastructure.settings import (
    BootstrapSettings,
    BotSettings,
    DatabaseSettings,
    Settings,
)


class TestDatabaseSettings:
    def test_default_url_is_postgres(self) -> None:
        s = DatabaseSettings()
        assert s.url.get_secret_value().startswith("postgresql+asyncpg://")

    def test_url_kept_secret(self) -> None:
        s = DatabaseSettings(url=SecretStr("postgresql+asyncpg://u:secret@host/db"))
        assert "secret" not in repr(s)

    def test_pool_validation(self) -> None:
        with pytest.raises(ValidationError):
            DatabaseSettings(pool_size=0)
        with pytest.raises(ValidationError):
            DatabaseSettings(max_overflow=-1)


class TestBootstrapSettings:
    def test_default_empty(self) -> None:
        s = BootstrapSettings()
        assert s.admin_ids == ()

    def test_csv_parsing(self) -> None:
        s = BootstrapSettings(admin_ids="100, 200, 300")  # type: ignore[arg-type]
        assert s.admin_ids == (100, 200, 300)

    def test_csv_parsing_handles_blanks(self) -> None:
        s = BootstrapSettings(admin_ids=" 100 ,, 200 ,")  # type: ignore[arg-type]
        assert s.admin_ids == (100, 200)

    def test_explicit_tuple_passes_through(self) -> None:
        s = BootstrapSettings(admin_ids=(7, 8, 9))
        assert s.admin_ids == (7, 8, 9)

    def test_empty_string_yields_empty_tuple(self) -> None:
        s = BootstrapSettings(admin_ids="")  # type: ignore[arg-type]
        assert s.admin_ids == ()

    def test_invalid_token_raises(self) -> None:
        with pytest.raises(ValidationError):
            BootstrapSettings(admin_ids="abc,def")  # type: ignore[arg-type]


class TestBotSettings:
    def test_default_token_is_placeholder(self) -> None:
        s = BotSettings()
        assert "placeholder" in s.token.get_secret_value()

    def test_token_kept_secret(self) -> None:
        s = BotSettings(token=SecretStr("123:ABCDEFsecret"))
        assert "ABCDEFsecret" not in repr(s)

    def test_throttle_validation_per_second_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            BotSettings(default_throttle_per_second=0)

    def test_throttle_validation_capacity_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            BotSettings(default_throttle_capacity=0)

    def test_explicit_values(self) -> None:
        s = BotSettings(
            token=SecretStr("123:tok"),
            default_throttle_per_second=2.5,
            default_throttle_capacity=4,
        )
        assert s.token.get_secret_value() == "123:tok"
        assert s.default_throttle_per_second == 2.5
        assert s.default_throttle_capacity == 4


class TestSettings:
    def test_compose(self) -> None:
        s = Settings(
            environment="dev",
            db=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")),
            bot=BotSettings(token=SecretStr("test-token")),
            bootstrap=BootstrapSettings(admin_ids=(42,)),
        )
        assert s.environment == "dev"
        assert s.db.url.get_secret_value() == "sqlite+aiosqlite:///:memory:"
        assert s.bot.token.get_secret_value() == "test-token"
        assert s.bootstrap.admin_ids == (42,)
