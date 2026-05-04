"""Юнит-тесты `YamlBalanceLoader` (Спринт 0.2.10)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.infrastructure.balance import YamlBalanceLoader
from pipirik_wars.shared.errors import ConfigError
from tests.unit.domain.balance.factories import valid_balance_payload


def _write_yaml(path: Path, payload: object) -> None:
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")


class TestLazyLoading:
    def test_constructor_does_not_read_file(self, tmp_path: Path) -> None:
        # ВАЖНО: путь не существует → конструктор не должен падать.
        loader = YamlBalanceLoader(tmp_path / "missing.yaml")
        assert loader.path == tmp_path / "missing.yaml"
        # Файл нужен только при `get()`/`reload()`.

    def test_get_loads_file_on_first_call(self, tmp_path: Path) -> None:
        path = tmp_path / "balance.yaml"
        _write_yaml(path, valid_balance_payload())
        loader = YamlBalanceLoader(path)
        cfg = loader.get()
        assert isinstance(cfg, BalanceConfig)
        assert cfg.version == 1


class TestCaching:
    def test_get_returns_cached_instance(self, tmp_path: Path) -> None:
        path = tmp_path / "balance.yaml"
        _write_yaml(path, valid_balance_payload())
        loader = YamlBalanceLoader(path)
        first = loader.get()
        second = loader.get()
        # тождественность — не просто равенство
        assert first is second

    def test_get_does_not_reread_after_external_change(self, tmp_path: Path) -> None:
        path = tmp_path / "balance.yaml"
        _write_yaml(path, valid_balance_payload())
        loader = YamlBalanceLoader(path)
        first = loader.get()
        # Подменили файл «из-под носа» — без reload() не должно влиять.
        changed = valid_balance_payload()
        changed["version"] = 2
        _write_yaml(path, changed)
        second = loader.get()
        assert second is first
        assert second.version == 1


class TestReload:
    def test_reload_refreshes_snapshot_atomically(self, tmp_path: Path) -> None:
        path = tmp_path / "balance.yaml"
        _write_yaml(path, valid_balance_payload())
        loader = YamlBalanceLoader(path)
        old = loader.get()

        changed = valid_balance_payload()
        changed["version"] = 2
        _write_yaml(path, changed)

        new = loader.reload()
        assert new is not old
        assert new.version == 2
        assert old.version == 1  # старый снимок остался валидным (frozen)
        # последующий get() возвращает новый снимок
        assert loader.get() is new

    def test_reload_failure_keeps_old_snapshot(self, tmp_path: Path) -> None:
        """Если новая версия yaml невалидна, кэш остаётся прежним (атомарность)."""
        path = tmp_path / "balance.yaml"
        _write_yaml(path, valid_balance_payload())
        loader = YamlBalanceLoader(path)
        old = loader.get()

        broken = valid_balance_payload()
        broken["display_names"] = [
            {"from": 5, "to": None, "name": "X"},  # не стартует с 0 → невалидно
        ]
        _write_yaml(path, broken)

        with pytest.raises(ConfigError):
            loader.reload()
        # старый снимок всё ещё валиден и доступен
        assert loader.get() is old


class TestErrorHandling:
    def test_missing_file_raises_config_error(self, tmp_path: Path) -> None:
        loader = YamlBalanceLoader(tmp_path / "nope.yaml")
        with pytest.raises(ConfigError, match="failed to read"):
            loader.get()

    def test_invalid_yaml_syntax_raises_config_error(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.yaml"
        path.write_text(":\n  - this is: not [valid yaml", encoding="utf-8")
        loader = YamlBalanceLoader(path)
        with pytest.raises(ConfigError, match="invalid YAML"):
            loader.get()

    def test_non_mapping_root_raises_config_error(self, tmp_path: Path) -> None:
        path = tmp_path / "list.yaml"
        path.write_text("- 1\n- 2\n- 3\n", encoding="utf-8")
        loader = YamlBalanceLoader(path)
        with pytest.raises(ConfigError, match="must be a YAML mapping"):
            loader.get()

    def test_validation_failure_raises_config_error(self, tmp_path: Path) -> None:
        path = tmp_path / "balance.yaml"
        broken = valid_balance_payload()
        # Дыра в display_names
        broken["display_names"] = [
            {"from": 0, "to": 10, "name": "A"},
            {"from": 20, "to": None, "name": "B"},
        ]
        _write_yaml(path, broken)
        loader = YamlBalanceLoader(path)
        with pytest.raises(ConfigError, match="invalid balance config"):
            loader.get()


class TestRealConfigBalanceYaml:
    def test_real_balance_yaml_loads(self) -> None:
        """Реальный `config/balance.yaml` валиден через loader."""
        repo_root = Path(__file__).resolve().parents[3]
        path = repo_root / "config" / "balance.yaml"
        loader = YamlBalanceLoader(path)
        cfg = loader.get()
        assert isinstance(cfg, BalanceConfig)
        assert cfg.display_names[0].from_cm == 0
        assert cfg.display_names[-1].to_cm is None
