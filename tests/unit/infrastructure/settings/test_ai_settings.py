"""Unit-тесты `AiSettings` (Спринт 4.1-M, шаг M.2).

Контракт:
* Дефолты: `enabled=False`, `api_key=None`, `model="gpt-4o-mini"`,
  `timeout_seconds=60.0`, `refresh_interval_hours=24.0`, batch_sizes
  по полям 30/30/20.
* Env-prefix `AI_`: `AI_ENABLED=true` поднимает флаг.
* `api_key` — `SecretStr`; реальное значение через `get_secret_value()`.
* Поля `timeout_seconds` / `refresh_interval_hours` имеют разумные
  границы (>= 1.0 / >= 0.5).
* `batch_size_*` ограничены ge=1, le=200.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from pipirik_wars.infrastructure.settings.ai import AiSettings


class TestAiSettingsDefaults:
    def test_defaults_are_disabled(self) -> None:
        s = AiSettings()
        assert s.enabled is False
        assert s.api_key is None
        assert s.model == "gpt-4o-mini"
        assert s.base_url is None

    def test_default_timings(self) -> None:
        s = AiSettings()
        assert s.timeout_seconds == 60.0
        assert s.refresh_interval_hours == 24.0

    def test_default_batch_sizes(self) -> None:
        s = AiSettings()
        assert s.batch_size_oracle == 30
        assert s.batch_size_forest == 30
        assert s.batch_size_duel == 20


class TestAiSettingsApiKey:
    def test_api_key_is_secret_str(self) -> None:
        s = AiSettings(api_key=SecretStr("sk-test-1234"))
        assert s.api_key is not None
        assert s.api_key.get_secret_value() == "sk-test-1234"

    def test_api_key_masked_in_repr(self) -> None:
        s = AiSettings(api_key=SecretStr("sk-test-1234"))
        rendered = repr(s)
        assert "sk-test-1234" not in rendered
        assert "**********" in rendered or "SecretStr" in rendered


class TestAiSettingsValidation:
    def test_timeout_seconds_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AiSettings(timeout_seconds=0.5)

    def test_timeout_seconds_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AiSettings(timeout_seconds=601.0)

    def test_refresh_interval_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AiSettings(refresh_interval_hours=0.4)

    def test_refresh_interval_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AiSettings(refresh_interval_hours=169.0)

    @pytest.mark.parametrize("field", ["batch_size_oracle", "batch_size_forest", "batch_size_duel"])
    def test_batch_size_below_min_rejected(self, field: str) -> None:
        with pytest.raises(ValidationError):
            AiSettings(**{field: 0})  # type: ignore[arg-type]

    @pytest.mark.parametrize("field", ["batch_size_oracle", "batch_size_forest", "batch_size_duel"])
    def test_batch_size_above_max_rejected(self, field: str) -> None:
        with pytest.raises(ValidationError):
            AiSettings(**{field: 201})  # type: ignore[arg-type]


class TestAiSettingsEnvLoading:
    def test_enabled_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_ENABLED", "true")
        monkeypatch.setenv("AI_API_KEY", "sk-test")
        monkeypatch.setenv("AI_MODEL", "gpt-4o")
        s = AiSettings()
        assert s.enabled is True
        assert s.api_key is not None
        assert s.api_key.get_secret_value() == "sk-test"
        assert s.model == "gpt-4o"

    def test_batch_sizes_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_BATCH_SIZE_ORACLE", "50")
        monkeypatch.setenv("AI_BATCH_SIZE_FOREST", "40")
        monkeypatch.setenv("AI_BATCH_SIZE_DUEL", "15")
        s = AiSettings()
        assert s.batch_size_oracle == 50
        assert s.batch_size_forest == 40
        assert s.batch_size_duel == 15
