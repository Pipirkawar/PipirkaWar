"""Unit-тесты `TgStarsSettings` (Спринт 4.1-D, шаг D.8.b).

Контракт:
* `secret` — обязательный, `SecretStr`, не может быть пустым; в `repr`
  маскируется.
* `payload_version` — по умолчанию `"v1"`, не пустой.
* `max_payload_bytes` — `1 <= ... <= 128` (лимит Telegram).
* Загружается из env с префиксом `TG_STARS_*`.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from pipirik_wars.infrastructure.payments.tg_stars.settings import TgStarsSettings


class TestTgStarsSettingsRequired:
    def test_secret_is_required(self) -> None:
        # Без env `TG_STARS_SECRET` и без явного `secret=...` —
        # `ValidationError` от pydantic.
        with pytest.raises(ValidationError):
            TgStarsSettings()  # type: ignore[call-arg]

    def test_empty_secret_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be non-empty"):
            TgStarsSettings(secret=SecretStr(""))

    def test_explicit_secret_accepted(self) -> None:
        s = TgStarsSettings(secret=SecretStr("super-strong-32+byte-test-secret"))
        assert isinstance(s.secret, SecretStr)
        assert s.secret.get_secret_value() == "super-strong-32+byte-test-secret"


class TestTgStarsSettingsDefaults:
    def test_payload_version_default_v1(self) -> None:
        s = TgStarsSettings(secret=SecretStr("any-test-secret-x"))
        assert s.payload_version == "v1"

    def test_max_payload_bytes_default_128(self) -> None:
        s = TgStarsSettings(secret=SecretStr("any-test-secret-x"))
        assert s.max_payload_bytes == 128


class TestTgStarsSettingsValidation:
    def test_empty_payload_version_raises(self) -> None:
        with pytest.raises(ValidationError, match="payload_version must be non-empty"):
            TgStarsSettings(
                secret=SecretStr("any-test-secret-x"),
                payload_version="",
            )

    def test_max_payload_bytes_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            TgStarsSettings(secret=SecretStr("any-test-secret-x"), max_payload_bytes=0)
        with pytest.raises(ValidationError):
            TgStarsSettings(secret=SecretStr("any-test-secret-x"), max_payload_bytes=-1)

    def test_max_payload_bytes_capped_at_128(self) -> None:
        # Telegram-лимит — 128 байт; больше — невалидно.
        with pytest.raises(ValidationError):
            TgStarsSettings(
                secret=SecretStr("any-test-secret-x"),
                max_payload_bytes=129,
            )

    def test_max_payload_bytes_lower_value_accepted(self) -> None:
        # Меньше лимита — допустимо (для тестов).
        s = TgStarsSettings(
            secret=SecretStr("any-test-secret-x"),
            max_payload_bytes=64,
        )
        assert s.max_payload_bytes == 64


class TestTgStarsSettingsSecrets:
    def test_secret_does_not_leak_in_repr(self) -> None:
        s = TgStarsSettings(secret=SecretStr("super-secret-don-t-show-me"))
        text = repr(s)
        assert "super-secret-don-t-show-me" not in text
        assert "SecretStr" in text


class TestTgStarsSettingsEnv:
    def test_loads_from_env_with_tg_stars_prefix(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TG_STARS_SECRET", "from-env-secret-32-byte-foo")
        monkeypatch.setenv("TG_STARS_PAYLOAD_VERSION", "v2")
        monkeypatch.setenv("TG_STARS_MAX_PAYLOAD_BYTES", "96")
        s = TgStarsSettings()  # type: ignore[call-arg]
        assert s.secret.get_secret_value() == "from-env-secret-32-byte-foo"
        assert s.payload_version == "v2"
        assert s.max_payload_bytes == 96
