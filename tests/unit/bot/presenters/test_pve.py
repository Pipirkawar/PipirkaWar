"""Юнит-тесты `bot/presenters/_pve.py` (Спринт 3.1-E, ГДД §8).

Покрываем оба kind-а PvE-локаций (`mountains`/`dungeon`) одной
параметризованной сюжетной линией:

1. Pure-функции `pve_callback_data` / `parse_pve_callback_data` /
   `is_pve_callback` — серилизация/парсинг `callback_data`,
   инварианты (≤ 64 байт, отказ на zero/negative `run_id`/`drop_idx`,
   отказ на unknown action, отказ на bad format).
2. `PvePresenter` через `FakeMessageBundle` — проверяем, что
   презентер просит правильные ключи (`<kind>-<suffix>`) и параметры.
3. `PvePresenter` через `FluentMessageBundle` (RU + EN) — реальные
   переводы (smoke).

Сами `MountainsPresenter` / `DungeonPresenter` — тонкие обёртки;
тестируем «параметризованный» PvePresenter напрямую — это покрывает
обе обёртки 1:1.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from pipirik_wars.application.dungeon import DungeonRunFinished
from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.mountains import MountainRunFinished
from pipirik_wars.bot.presenters._pve import (
    PveCallbackAction,
    PveCallbackData,
    PvePresenter,
    is_pve_callback,
    parse_pve_callback_data,
    pve_callback_data,
)
from pipirik_wars.domain.dungeon import DungeonRun, DungeonRunStatus
from pipirik_wars.domain.mountains import MountainRun, MountainRunStatus
from pipirik_wars.domain.player import (
    DisplayName,
    Length,
    Player,
    PlayerName,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.domain.pve import Item, PveItemDrop, PveLocationKind, Rarity, Slot
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_RU = Locale("ru")
_EN = Locale("en")


def _player(*, length_cm: int = 47, name: PlayerName | None = None) -> Player:
    return Player(
        id=1,
        tg_id=100,
        username=Username(value="alice"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=3),
        title=None,
        name=name,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _item(*, item_id: str = "item.head.cap", display: str = "Cap") -> Item:
    return Item(id=item_id, display_name=display, slot=Slot.HAT, rarity=Rarity.COMMON)


def _mountain_run(
    *,
    rid: int = 11,
    length_delta_cm: int = 5,
    drops: tuple[PveItemDrop, ...] = (),
) -> MountainRun:
    return MountainRun(
        id=rid,
        player_id=1,
        status=MountainRunStatus.FINISHED,
        started_at=_NOW - timedelta(minutes=15),
        ends_at=_NOW,
        finished_at=_NOW,
        branch_name="normal_gain",
        length_delta_cm=length_delta_cm,
        drops=drops,
    )


def _dungeon_run(
    *,
    rid: int = 11,
    length_delta_cm: int = 5,
    drops: tuple[PveItemDrop, ...] = (),
) -> DungeonRun:
    return DungeonRun(
        id=rid,
        player_id=1,
        status=DungeonRunStatus.FINISHED,
        started_at=_NOW - timedelta(minutes=15),
        ends_at=_NOW,
        finished_at=_NOW,
        branch_name="normal_gain",
        length_delta_cm=length_delta_cm,
        drops=drops,
    )


def _mountain_finished(
    *,
    length_delta_cm: int = 5,
    drops: tuple[PveItemDrop, ...] = (),
    was_already_finished: bool = False,
    rid: int = 11,
) -> MountainRunFinished:
    before = _player(length_cm=42)
    after = _player(length_cm=42 + length_delta_cm)
    return MountainRunFinished(
        run=_mountain_run(rid=rid, length_delta_cm=length_delta_cm, drops=drops),
        player_before=before,
        player_after=after,
        was_already_finished=was_already_finished,
    )


def _dungeon_finished(
    *,
    length_delta_cm: int = 5,
    drops: tuple[PveItemDrop, ...] = (),
    was_already_finished: bool = False,
    rid: int = 11,
) -> DungeonRunFinished:
    before = _player(length_cm=42)
    after = _player(length_cm=42 + length_delta_cm)
    return DungeonRunFinished(
        run=_dungeon_run(rid=rid, length_delta_cm=length_delta_cm, drops=drops),
        player_before=before,
        player_after=after,
        was_already_finished=was_already_finished,
    )


def _fluent_bundle() -> IMessageBundle:
    return FluentMessageBundle(locales_dir=Path(__file__).resolve().parents[4] / "locales")


# ============================================================
# Pure-функции: callback_data
# ============================================================


class TestCallbackData:
    @pytest.mark.parametrize("kind", [PveLocationKind.MOUNTAINS, PveLocationKind.DUNGEON])
    @pytest.mark.parametrize("action", ["equip_item", "drop_item"])
    def test_round_trip(self, kind: PveLocationKind, action: str) -> None:
        action_typed = cast(PveCallbackAction, action)
        raw = pve_callback_data(kind=kind, action=action_typed, run_id=42, drop_idx=1)
        parsed = parse_pve_callback_data(raw)
        assert parsed == PveCallbackData(kind=kind, action=action_typed, run_id=42, drop_idx=1)

    def test_serialize_format_mountains(self) -> None:
        assert (
            pve_callback_data(
                kind=PveLocationKind.MOUNTAINS,
                action="equip_item",
                run_id=7,
                drop_idx=0,
            )
            == "mountains:equip_item:7:0"
        )

    def test_serialize_format_dungeon(self) -> None:
        assert (
            pve_callback_data(
                kind=PveLocationKind.DUNGEON,
                action="drop_item",
                run_id=99,
                drop_idx=2,
            )
            == "dungeon:drop_item:99:2"
        )

    def test_serialize_under_64_bytes_for_max_int(self) -> None:
        big = pve_callback_data(
            kind=PveLocationKind.MOUNTAINS,
            action="drop_item",
            run_id=9_999_999_999_999_999_999,
            drop_idx=99,
        )
        assert len(big.encode()) <= 64

    def test_serialize_rejects_zero_or_negative_run_id(self) -> None:
        with pytest.raises(ValueError):
            pve_callback_data(
                kind=PveLocationKind.MOUNTAINS, action="equip_item", run_id=0, drop_idx=0
            )
        with pytest.raises(ValueError):
            pve_callback_data(
                kind=PveLocationKind.MOUNTAINS, action="equip_item", run_id=-1, drop_idx=0
            )

    def test_serialize_rejects_negative_drop_idx(self) -> None:
        with pytest.raises(ValueError):
            pve_callback_data(
                kind=PveLocationKind.MOUNTAINS, action="equip_item", run_id=1, drop_idx=-1
            )

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "mountains",
            "mountains:equip_item",
            "mountains:equip_item:1",
            "mountains:equip_item:1:0:extra",
            "x:equip_item:1:0",
            "forest:equip_item:1:0",
        ],
    )
    def test_parse_rejects_malformed_format(self, raw: str) -> None:
        with pytest.raises(ValueError):
            parse_pve_callback_data(raw)

    def test_parse_rejects_unknown_action(self) -> None:
        with pytest.raises(ValueError):
            parse_pve_callback_data("mountains:eat_item:1:0")

    def test_parse_rejects_non_numeric(self) -> None:
        with pytest.raises(ValueError):
            parse_pve_callback_data("mountains:equip_item:abc:0")
        with pytest.raises(ValueError):
            parse_pve_callback_data("mountains:equip_item:1:abc")

    def test_parse_rejects_zero_or_negative_run_id(self) -> None:
        with pytest.raises(ValueError):
            parse_pve_callback_data("mountains:equip_item:0:0")
        with pytest.raises(ValueError):
            parse_pve_callback_data("dungeon:drop_item:-1:0")

    def test_is_pve_callback(self) -> None:
        assert is_pve_callback("mountains:equip_item:1:0") is True
        assert is_pve_callback("dungeon:drop_item:1:0") is True
        assert is_pve_callback("forest:apply_name:1") is False
        assert is_pve_callback("upgrade:1") is False
        assert is_pve_callback("") is False


# ============================================================
# PvePresenter — FakeMessageBundle (маркеры)
# ============================================================


class TestPvePresenterFakeBundle:
    @pytest.mark.parametrize(
        "kind, prefix",
        [
            (PveLocationKind.MOUNTAINS, "mountains"),
            (PveLocationKind.DUNGEON, "dungeon"),
        ],
    )
    def test_basic_keys_use_kind_prefix(self, kind: PveLocationKind, prefix: str) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=kind)
        assert presenter.group(locale=_RU) == f"ru:{prefix}-group"
        assert presenter.other(locale=_RU) == f"ru:{prefix}-other"
        assert presenter.not_registered(locale=_RU) == f"ru:{prefix}-not-registered"
        assert presenter.already_in(locale=_RU) == f"ru:{prefix}-already-in"

    @pytest.mark.parametrize("kind", [PveLocationKind.MOUNTAINS, PveLocationKind.DUNGEON])
    def test_requirement_thickness_passes_args(self, kind: PveLocationKind) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=kind)
        text = presenter.requirement_thickness(required=3, actual=1, locale=_RU)
        assert "requirement-thickness" in text
        assert "required=3" in text
        assert "actual=1" in text

    @pytest.mark.parametrize("kind", [PveLocationKind.MOUNTAINS, PveLocationKind.DUNGEON])
    def test_requirement_length_passes_args(self, kind: PveLocationKind) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=kind)
        text = presenter.requirement_length(required_cm=20, actual_cm=15, locale=_RU)
        assert "requirement-length" in text
        assert "required_cm=20" in text
        assert "actual_cm=15" in text

    def test_started_passes_nick_and_cooldown(self) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=PveLocationKind.MOUNTAINS)
        text = presenter.started(
            player=_player(),
            display_name=DisplayName(value="Пипирик"),
            cooldown_minutes=30,
            locale=_RU,
        )
        assert "ru:mountains-started" in text
        assert "nick=Пипирик" in text
        assert "cooldown_minutes=30" in text

    def test_started_fallback_passes_cooldown(self) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=PveLocationKind.DUNGEON)
        text = presenter.started_fallback(cooldown_minutes=45, locale=_EN)
        assert "en:dungeon-started-fallback" in text
        assert "cooldown_minutes=45" in text

    def test_finished_gain_branch_used(self) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=PveLocationKind.MOUNTAINS)
        result = _mountain_finished(length_delta_cm=5)
        text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
            locale=_RU,
        )
        assert "mountains-finished-header" in text
        assert "mountains-finished-length-gain" in text
        assert "length_delta_cm=5" in text

    def test_finished_loss_branch_used(self) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=PveLocationKind.MOUNTAINS)
        result = _mountain_finished(length_delta_cm=-7)
        text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
            locale=_RU,
        )
        assert "mountains-finished-length-loss" in text
        # abs-значение не должно повторно содержать минус (рендер делает «−»)
        assert "length_delta_abs_cm=7" in text

    def test_finished_zero_branch_used(self) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=PveLocationKind.DUNGEON)
        result = _dungeon_finished(length_delta_cm=0)
        text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
            locale=_RU,
        )
        assert "dungeon-finished-length-zero" in text

    def test_finished_renders_drops(self) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=PveLocationKind.MOUNTAINS)
        drops = (
            PveItemDrop(item=_item(item_id="item.head.cap", display="Cap")),
            PveItemDrop(item=_item(item_id="item.head.helm", display="Helm")),
        )
        result = _mountain_finished(length_delta_cm=5, drops=drops)
        text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
            locale=_RU,
        )
        # Каждый дроп — отдельная строка через ключ `<kind>-finished-item-found`.
        assert text.count("mountains-finished-item-found") == 2
        assert "Cap" in text
        assert "Helm" in text


class TestFinishKeyboard:
    def test_keyboard_none_when_no_drops(self) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=PveLocationKind.MOUNTAINS)
        assert presenter.finish_keyboard(_mountain_finished(), locale=_RU) is None

    def test_keyboard_has_two_buttons_per_drop_mountains(self) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=PveLocationKind.MOUNTAINS)
        drops = (PveItemDrop(item=_item()), PveItemDrop(item=_item(item_id="i2", display="X2")))
        result = _mountain_finished(drops=drops)
        kb = presenter.finish_keyboard(result, locale=_RU)
        assert kb is not None
        # 2 ряда (по одному на дроп), в каждом 2 кнопки (надеть/выбросить).
        assert len(kb.inline_keyboard) == 2
        for row in kb.inline_keyboard:
            assert len(row) == 2
        # callback_data всех кнопок в формате `mountains:<action>:<run_id>:<idx>`
        for idx, row in enumerate(kb.inline_keyboard):
            for btn in row:
                assert btn.callback_data is not None
                assert btn.callback_data.startswith("mountains:")
                assert btn.callback_data.endswith(f":{idx}")

    def test_keyboard_uses_dungeon_prefix(self) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=PveLocationKind.DUNGEON)
        drops = (PveItemDrop(item=_item()),)
        result = _dungeon_finished(drops=drops)
        kb = presenter.finish_keyboard(result, locale=_RU)
        assert kb is not None
        for btn in kb.inline_keyboard[0]:
            assert btn.callback_data is not None
            assert btn.callback_data.startswith("dungeon:")


class TestToasts:
    @pytest.mark.parametrize(
        "kind, prefix",
        [
            (PveLocationKind.MOUNTAINS, "mountains"),
            (PveLocationKind.DUNGEON, "dungeon"),
        ],
    )
    def test_toast_keys(self, kind: PveLocationKind, prefix: str) -> None:
        presenter = PvePresenter(bundle=FakeMessageBundle(), kind=kind)
        assert (
            presenter.toast_item_equipped_placeholder(locale=_RU)
            == f"ru:{prefix}-toast-item-equipped-placeholder"
        )
        assert presenter.toast_item_dropped(locale=_RU) == f"ru:{prefix}-toast-item-dropped"
        assert presenter.toast_foreign_button(locale=_RU) == f"ru:{prefix}-toast-foreign-button"
        assert presenter.toast_run_not_found(locale=_RU) == f"ru:{prefix}-toast-run-not-found"
        assert presenter.toast_drop_mismatch(locale=_RU) == f"ru:{prefix}-toast-drop-mismatch"


# ============================================================
# Smoke: реальные fluent-переводы для обоих локалей
# ============================================================


class TestFluentBundleSmoke:
    @pytest.mark.parametrize("kind", [PveLocationKind.MOUNTAINS, PveLocationKind.DUNGEON])
    def test_started_renders_in_both_locales(self, kind: PveLocationKind) -> None:
        presenter = PvePresenter(bundle=_fluent_bundle(), kind=kind)
        ru_text = presenter.started(
            player=_player(),
            display_name=DisplayName(value="Пипирик"),
            cooldown_minutes=15,
            locale=_RU,
        )
        en_text = presenter.started(
            player=_player(),
            display_name=DisplayName(value="Pippy"),
            cooldown_minutes=15,
            locale=_EN,
        )
        assert "Пипирик" in ru_text
        assert "Pippy" in en_text
        # Кооldown render
        assert "15" in ru_text
        assert "15" in en_text

    def test_requirement_renders_in_both_locales(self) -> None:
        presenter = PvePresenter(bundle=_fluent_bundle(), kind=PveLocationKind.MOUNTAINS)
        ru_text = presenter.requirement_thickness(required=3, actual=1, locale=_RU)
        en_text = presenter.requirement_thickness(required=3, actual=1, locale=_EN)
        assert "3" in ru_text
        assert "3" in en_text

    @pytest.mark.parametrize("kind", [PveLocationKind.MOUNTAINS, PveLocationKind.DUNGEON])
    def test_finished_renders_in_both_locales(self, kind: PveLocationKind) -> None:
        presenter = PvePresenter(bundle=_fluent_bundle(), kind=kind)
        result = (
            _mountain_finished(length_delta_cm=5)
            if kind is PveLocationKind.MOUNTAINS
            else _dungeon_finished(length_delta_cm=5)
        )
        ru_text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
            locale=_RU,
        )
        en_text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Pippy"),
            locale=_EN,
        )
        # Длина изменилась +5 — оба перевода должны содержать «5».
        assert "5" in ru_text
        assert "5" in en_text
