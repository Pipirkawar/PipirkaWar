"""Интеграционные тесты `YamlBalanceWriter` (Спринт 2.5-C.4)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pipirik_wars.domain.balance.errors import BalanceKeyError
from pipirik_wars.infrastructure.balance.loader import YamlBalanceLoader
from pipirik_wars.infrastructure.balance.writer import YamlBalanceWriter
from pipirik_wars.shared.errors import ConfigError
from tests.unit.domain.balance.factories import valid_balance_payload


def _seed_balance_yaml(tmp_path: Path) -> Path:
    """Записать valid balance.yaml в tmp dir и вернуть путь."""
    balance_path = tmp_path / "balance.yaml"
    balance_path.write_text(
        yaml.safe_dump(valid_balance_payload(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return balance_path


class TestYamlBalanceWriter:
    def test_set_top_level_scalar_persists_and_reloads(self, tmp_path: Path) -> None:
        path = _seed_balance_yaml(tmp_path)
        loader = YamlBalanceLoader(path)
        loader.get()  # cache initial
        writer = YamlBalanceWriter(path=path, loader=loader)

        new_snapshot = writer.write_value(key="version", raw_value=2)

        # Возвращённый снимок отражает новое значение.
        assert new_snapshot.version == 2
        # Loader тоже синхронизирован (auto-reload).
        assert loader.get().version == 2
        # Файл реально перезаписан.
        with path.open(encoding="utf-8") as fh:
            on_disk = yaml.safe_load(fh)
        assert on_disk["version"] == 2

    def test_set_nested_scalar(self, tmp_path: Path) -> None:
        path = _seed_balance_yaml(tmp_path)
        loader = YamlBalanceLoader(path)
        writer = YamlBalanceWriter(path=path, loader=loader)

        # forest.cooldown_min_minutes = 10 (factories) → 20
        new_snapshot = writer.write_value(
            key="forest.cooldown_min_minutes",
            raw_value=20,
        )
        assert new_snapshot.forest.cooldown_min_minutes == 20
        assert loader.get().forest.cooldown_min_minutes == 20

    def test_set_dict_value(self, tmp_path: Path) -> None:
        path = _seed_balance_yaml(tmp_path)
        loader = YamlBalanceLoader(path)
        writer = YamlBalanceWriter(path=path, loader=loader)

        # Изменить весь thickness.unlock_levels одним блоком.
        new_levels = {"forest": 1, "pvp_chat": 3, "mountains": 5}
        new_snapshot = writer.write_value(
            key="thickness.unlock_levels",
            raw_value=new_levels,
        )
        assert new_snapshot.thickness.unlock_levels == new_levels

    def test_invalid_value_does_not_modify_file(self, tmp_path: Path) -> None:
        path = _seed_balance_yaml(tmp_path)
        loader = YamlBalanceLoader(path)
        writer = YamlBalanceWriter(path=path, loader=loader)
        original = path.read_text(encoding="utf-8")

        # version=0 нарушит pydantic-инвариант (Field(ge=1)).
        with pytest.raises(ConfigError):
            writer.write_value(key="version", raw_value=0)

        # Файл не изменён, в loader-е старое значение (даже после reload).
        assert path.read_text(encoding="utf-8") == original
        assert loader.reload().version == 1

    def test_unknown_key_raises_balance_key_error(self, tmp_path: Path) -> None:
        path = _seed_balance_yaml(tmp_path)
        loader = YamlBalanceLoader(path)
        writer = YamlBalanceWriter(path=path, loader=loader)
        original = path.read_text(encoding="utf-8")

        with pytest.raises(BalanceKeyError) as ctx:
            writer.write_value(key="unknown_section", raw_value=1)
        assert ctx.value.reason == "not_found"
        # Файл не изменён.
        assert path.read_text(encoding="utf-8") == original

    def test_index_out_of_range(self, tmp_path: Path) -> None:
        path = _seed_balance_yaml(tmp_path)
        loader = YamlBalanceLoader(path)
        writer = YamlBalanceWriter(path=path, loader=loader)

        with pytest.raises(BalanceKeyError) as ctx:
            writer.write_value(key="display_names.99.name", raw_value="X")
        assert ctx.value.reason == "index_invalid"

    def test_two_sequential_writes_last_write_wins(self, tmp_path: Path) -> None:
        # Имитация конкурирующих /balance_set: последний write побеждает.
        path = _seed_balance_yaml(tmp_path)
        loader = YamlBalanceLoader(path)
        writer = YamlBalanceWriter(path=path, loader=loader)

        writer.write_value(key="version", raw_value=2)
        writer.write_value(key="version", raw_value=3)

        assert loader.get().version == 3
        with path.open(encoding="utf-8") as fh:
            assert yaml.safe_load(fh)["version"] == 3

    def test_no_orphan_tmp_files_after_success(self, tmp_path: Path) -> None:
        path = _seed_balance_yaml(tmp_path)
        loader = YamlBalanceLoader(path)
        writer = YamlBalanceWriter(path=path, loader=loader)

        writer.write_value(key="version", raw_value=2)

        # В директории должны остаться только balance.yaml + lock-file.
        files = sorted(p.name for p in tmp_path.iterdir())
        # tmp-файлы writer-а имеют префикс `.balance.yaml.` + suffix `.tmp`.
        tmp_files = [f for f in files if f.startswith(".balance.yaml.") and f.endswith(".tmp")]
        assert tmp_files == []
