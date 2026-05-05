"""Unit-тесты доменных сущностей `/oracle`."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pipirik_wars.domain.oracle import OracleResult, OracleTemplate


class TestOracleTemplate:
    def test_valid(self) -> None:
        t = OracleTemplate(id="oracle.ru.0001", text="Сегодня всё хорошо, {user}!")
        assert t.id == "oracle.ru.0001"
        assert "{user}" in t.text

    @pytest.mark.parametrize("bad_id", ["", " ", "  oracle.ru.0001  "])
    def test_id_must_be_non_empty_and_stripped(self, bad_id: str) -> None:
        with pytest.raises(ValueError):
            OracleTemplate(id=bad_id, text="ok")

    @pytest.mark.parametrize("bad_text", ["", " text"])
    def test_text_must_be_non_empty_and_stripped(self, bad_text: str) -> None:
        with pytest.raises(ValueError):
            OracleTemplate(id="oracle.ru.0001", text=bad_text)

    def test_frozen(self) -> None:
        t = OracleTemplate(id="t", text="x")
        with pytest.raises(FrozenInstanceError):
            t.__setattr__("id", "y")


class TestOracleResult:
    def test_holds_bonus_and_template(self) -> None:
        tpl = OracleTemplate(id="t", text="x")
        res = OracleResult(bonus_cm=7, template=tpl)
        assert res.bonus_cm == 7
        assert res.template is tpl
