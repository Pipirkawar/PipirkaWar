"""Unit tests for balance route helpers (Sprint 4.5-G)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pipirik_wars.admin_web.routes.balance import (
    _atomic_write_yaml,
    _section_names,
    _section_to_raw,
    _section_to_yaml,
)
from pipirik_wars.domain.balance.config import BalanceConfig
from tests.unit.domain.balance.factories import valid_balance_payload


def _make_config(overrides: dict[str, Any] | None = None) -> BalanceConfig:
    payload = valid_balance_payload()
    if overrides:
        payload.update(overrides)
    return BalanceConfig.model_validate(payload)


class TestSectionNames:
    def test_returns_all_balance_config_fields(self) -> None:
        names = _section_names()
        assert "version" in names
        assert "display_names" in names
        assert "forest" in names
        assert "items_catalog" in names
        assert "names_catalog" in names

    def test_matches_model_fields(self) -> None:
        names = _section_names()
        assert names == list(BalanceConfig.model_fields.keys())


class TestSectionToRaw:
    def test_scalar_section(self) -> None:
        cfg = _make_config()
        raw = _section_to_raw(cfg, "version")
        assert raw == 1

    def test_model_section_returns_dict(self) -> None:
        cfg = _make_config()
        raw = _section_to_raw(cfg, "forest")
        assert isinstance(raw, dict)
        assert "outcomes" in raw
        assert "cooldown_min_minutes" in raw

    def test_tuple_section_returns_list(self) -> None:
        cfg = _make_config()
        raw = _section_to_raw(cfg, "display_names")
        assert isinstance(raw, list)
        assert len(raw) >= 3
        assert raw[0]["name"] == "Пипирик"

    def test_names_catalog_returns_list_of_strings(self) -> None:
        cfg = _make_config()
        raw = _section_to_raw(cfg, "names_catalog")
        assert isinstance(raw, list)
        assert all(isinstance(n, str) for n in raw)


class TestSectionToYaml:
    def test_returns_valid_yaml_string(self) -> None:
        cfg = _make_config()
        text = _section_to_yaml(cfg, "forest")
        assert isinstance(text, str)
        parsed = yaml.safe_load(text)
        assert isinstance(parsed, dict)
        assert "outcomes" in parsed

    def test_version_roundtrip(self) -> None:
        cfg = _make_config()
        text = _section_to_yaml(cfg, "version")
        parsed = yaml.safe_load(text)
        assert parsed == 1

    def test_display_names_roundtrip(self) -> None:
        cfg = _make_config()
        text = _section_to_yaml(cfg, "display_names")
        parsed = yaml.safe_load(text)
        assert isinstance(parsed, list)
        assert parsed[0]["from"] == 0
        assert parsed[0]["name"] == "Пипирик"

    def test_names_catalog_roundtrip(self) -> None:
        cfg = _make_config()
        text = _section_to_yaml(cfg, "names_catalog")
        parsed = yaml.safe_load(text)
        assert isinstance(parsed, list)
        assert len(parsed) >= 30


class TestAtomicWriteYaml:
    def test_writes_file_atomically(self, tmp_path: Path) -> None:
        path = tmp_path / "test.yaml"
        data: dict[str, Any] = {"version": 42, "key": "value"}
        _atomic_write_yaml(path, data)
        assert path.exists()
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert loaded["version"] == 42
        assert loaded["key"] == "value"

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "test.yaml"
        _atomic_write_yaml(path, {"version": 1})
        _atomic_write_yaml(path, {"version": 2})
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert loaded["version"] == 2
