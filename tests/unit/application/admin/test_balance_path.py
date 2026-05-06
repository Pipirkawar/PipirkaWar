"""Unit-тесты `_balance_path` (Спринт 2.5-C.3)."""

from __future__ import annotations

import pytest

from pipirik_wars.application.admin._balance_path import (
    BalanceKeyError,
    lookup_path,
    lookup_raw_node,
)
from pipirik_wars.domain.balance.config import BalanceConfig, ThicknessConfig
from tests.unit.domain.balance.factories import valid_balance_payload


@pytest.fixture
def cfg() -> BalanceConfig:
    return BalanceConfig.model_validate(valid_balance_payload())


class TestLookupPath:
    def test_scalar_int(self, cfg: BalanceConfig) -> None:
        assert lookup_path(cfg, "version") == 1

    def test_nested_int(self, cfg: BalanceConfig) -> None:
        # forest.cooldown_min_minutes (см. factories)
        result = lookup_path(cfg, "forest.cooldown_min_minutes")
        assert isinstance(result, int)

    def test_nested_dict(self, cfg: BalanceConfig) -> None:
        # thickness.unlock_levels — это dict[str, int]
        result = lookup_path(cfg, "thickness.unlock_levels")
        assert isinstance(result, dict)
        assert result == {"forest": 1, "pvp_chat": 2, "mountains": 3}

    def test_dict_value_lookup(self, cfg: BalanceConfig) -> None:
        # Можно нырнуть внутрь dict-а
        assert lookup_path(cfg, "thickness.unlock_levels.forest") == 1

    def test_pydantic_model_returns_dict(self, cfg: BalanceConfig) -> None:
        result = lookup_path(cfg, "thickness")
        assert isinstance(result, dict)
        assert result["cost_base"] == 1000

    def test_tuple_indexed_access(self, cfg: BalanceConfig) -> None:
        # display_names — tuple[DisplayNameRange, ...]
        result = lookup_path(cfg, "display_names.0")
        assert isinstance(result, dict)
        assert result["from"] == 0  # alias of from_cm

    def test_tuple_field_access_after_index(self, cfg: BalanceConfig) -> None:
        result = lookup_path(cfg, "display_names.0.name")
        assert result == "Пипирик"

    def test_pydantic_alias_supported_for_navigation(self, cfg: BalanceConfig) -> None:
        # Navigation поддерживает alias-ы: можно писать `from` (alias of from_cm).
        assert lookup_path(cfg, "display_names.0.from") == 0
        # Real-name тоже работает.
        assert lookup_path(cfg, "display_names.0.from_cm") == 0

    def test_empty_key_raises(self, cfg: BalanceConfig) -> None:
        with pytest.raises(BalanceKeyError) as ctx:
            lookup_path(cfg, "")
        assert ctx.value.reason == "empty"

    def test_whitespace_key_raises(self, cfg: BalanceConfig) -> None:
        with pytest.raises(BalanceKeyError) as ctx:
            lookup_path(cfg, "   ")
        assert ctx.value.reason == "empty"

    def test_unknown_top_level_segment_raises(self, cfg: BalanceConfig) -> None:
        with pytest.raises(BalanceKeyError) as ctx:
            lookup_path(cfg, "unknown_section")
        assert ctx.value.reason == "not_found"
        assert ctx.value.segment == "unknown_section"

    def test_unknown_nested_segment_raises(self, cfg: BalanceConfig) -> None:
        with pytest.raises(BalanceKeyError) as ctx:
            lookup_path(cfg, "forest.does_not_exist")
        assert ctx.value.reason == "not_found"

    def test_index_out_of_range(self, cfg: BalanceConfig) -> None:
        with pytest.raises(BalanceKeyError) as ctx:
            lookup_path(cfg, "display_names.999")
        assert ctx.value.reason == "index_invalid"

    def test_negative_index_rejected(self, cfg: BalanceConfig) -> None:
        with pytest.raises(BalanceKeyError) as ctx:
            lookup_path(cfg, "display_names.-1")
        assert ctx.value.reason == "index_invalid"

    def test_non_int_segment_on_tuple(self, cfg: BalanceConfig) -> None:
        with pytest.raises(BalanceKeyError) as ctx:
            lookup_path(cfg, "display_names.foo")
        assert ctx.value.reason == "not_found"

    def test_segment_after_scalar_raises(self, cfg: BalanceConfig) -> None:
        with pytest.raises(BalanceKeyError) as ctx:
            lookup_path(cfg, "version.something")
        assert ctx.value.reason == "not_found"

    def test_empty_segment_in_middle(self, cfg: BalanceConfig) -> None:
        with pytest.raises(BalanceKeyError) as ctx:
            lookup_path(cfg, "forest..cooldown_min_minutes")
        assert ctx.value.reason == "empty_segment"


class TestLookupRawNode:
    def test_returns_pydantic_model(self, cfg: BalanceConfig) -> None:
        node = lookup_raw_node(cfg, "thickness")
        assert isinstance(node, ThicknessConfig)

    def test_returns_scalar(self, cfg: BalanceConfig) -> None:
        node = lookup_raw_node(cfg, "thickness.cost_base")
        assert node == 1000
