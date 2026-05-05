"""Юнит-тесты `OraclePresenter` (Спринт 1.4.B → 1.5.D, ПД 1.4.4).

Покрываем:

1. **chat-ветки** (`group`/`other`/`not_registered`) — что вызывают
   правильные ключи `oracle-*`.
2. **`success`** — подстановка `{user}` в шаблон + параметры
   `bonus_cm`/`new_length_cm`/`prediction`.
3. **`already_used`** — расчёт часов/минут до 00:00 МСК.
4. Интеграция с `FluentMessageBundle`: проверяем человекочитаемый
   текст для RU/EN.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters.oracle import OraclePresenter
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle


def _fluent_bundle() -> IMessageBundle:
    return FluentMessageBundle(locales_dir=Path(__file__).resolve().parents[4] / "locales")


class TestOraclePresenterFakeBundle:
    """Маркерный bundle: проверяем, какие ключи зовёт презентер."""

    def _make(self) -> OraclePresenter:
        return OraclePresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))

    def test_group_uses_oracle_group_key(self) -> None:
        assert self._make().group(locale=Locale("ru")) == "ru:oracle-group"

    def test_other_uses_oracle_other_key(self) -> None:
        assert self._make().other(locale=Locale("en")) == "en:oracle-other"

    def test_not_registered_uses_oracle_not_registered_key(self) -> None:
        assert self._make().not_registered(locale=Locale("ru")) == "ru:oracle-not-registered"

    def test_success_passes_substituted_template_as_prediction(self) -> None:
        out = self._make().success(
            template_text="Сегодня всё хорошо, {user}!",
            bonus_cm=7,
            new_length_cm=37,
            user_display="Алиса",
            locale=Locale("ru"),
        )
        # FakeMessageBundle сериализует params в `[k=v,...]`. Шаблон
        # уже должен быть с подменённым `{user}` на «Алиса».
        assert "ru:oracle-success[" in out
        assert "prediction=Сегодня всё хорошо, Алиса!" in out
        assert "bonus_cm=7" in out
        assert "new_length_cm=37" in out

    def test_success_template_without_placeholder_passthrough(self) -> None:
        out = self._make().success(
            template_text="Просто предсказание без имени.",
            bonus_cm=1,
            new_length_cm=11,
            user_display="Боб",
            locale=Locale("ru"),
        )
        assert "prediction=Просто предсказание без имени." in out

    def test_success_unknown_placeholder_kept_as_is(self) -> None:
        # `{stranger}` — не наш плейсхолдер; не падаем с KeyError.
        out = self._make().success(
            template_text="Hello {stranger}",
            bonus_cm=2,
            new_length_cm=12,
            user_display="Боб",
            locale=Locale("ru"),
        )
        assert "{stranger}" in out

    def test_already_used_passes_hours_and_minutes(self) -> None:
        out = self._make().already_used(
            moscow_date=date(2026, 5, 5),
            now=datetime(2026, 5, 5, 12, 0, tzinfo=UTC),  # 15:00 МСК → 9 часов до 00:00
            locale=Locale("ru"),
        )
        assert "ru:oracle-already-used[" in out
        assert "hours=9" in out
        # Минуты форматируются с ведущим нулём.
        assert "minutes=00" in out

    def test_already_used_zero_when_already_past_reset(self) -> None:
        out = self._make().already_used(
            moscow_date=date(2026, 5, 5),
            now=datetime(2026, 5, 5, 23, 0, tzinfo=UTC),  # 02:00 МСК следующего дня
            locale=Locale("ru"),
        )
        assert "hours=0" in out
        assert "minutes=00" in out


class TestOraclePresenterFluent:
    """Интеграционный рендер через настоящий `FluentMessageBundle`."""

    def _make(self) -> OraclePresenter:
        return OraclePresenter(bundle=_fluent_bundle())

    def test_success_ru_includes_prediction_and_lengths(self) -> None:
        text = self._make().success(
            template_text="Сегодня всё хорошо, {user}!",
            bonus_cm=7,
            new_length_cm=37,
            user_display="Алиса",
            locale=Locale("ru"),
        )
        assert "Сегодня всё хорошо, Алиса!" in text
        assert "+7 см" in text
        assert "37 см" in text

    def test_success_en_includes_prediction_and_lengths(self) -> None:
        text = self._make().success(
            template_text="Today is great, {user}!",
            bonus_cm=3,
            new_length_cm=15,
            user_display="Alice",
            locale=Locale("en"),
        )
        assert "Today is great, Alice!" in text
        assert "+3 cm" in text
        assert "15 cm" in text

    def test_already_used_ru_includes_hours_and_moscow_label(self) -> None:
        text = self._make().already_used(
            moscow_date=date(2026, 5, 5),
            now=datetime(2026, 5, 5, 12, 0, tzinfo=UTC),  # 15:00 МСК → 9 часов
            locale=Locale("ru"),
        )
        assert "9ч" in text
        assert "00:00 по Москве" in text

    def test_already_used_en_includes_hours_and_moscow_label(self) -> None:
        text = self._make().already_used(
            moscow_date=date(2026, 5, 5),
            now=datetime(2026, 5, 5, 12, 0, tzinfo=UTC),
            locale=Locale("en"),
        )
        assert "9h" in text
        assert "Moscow" in text

    def test_already_used_zero_after_reset(self) -> None:
        text = self._make().already_used(
            moscow_date=date(2026, 5, 5),
            now=datetime(2026, 5, 5, 23, 0, tzinfo=UTC),
            locale=Locale("ru"),
        )
        assert "0ч 00м" in text

    def test_group_other_not_registered_distinct_ru(self) -> None:
        p = self._make()
        ru = Locale("ru")
        texts = {p.group(locale=ru), p.other(locale=ru), p.not_registered(locale=ru)}
        assert len(texts) == 3

    def test_group_other_not_registered_localized_en(self) -> None:
        p = self._make()
        en = Locale("en")
        # EN-варианты должны явно быть локализованы (не идти в RU-fallback).
        assert "DM" in p.group(locale=en)
        assert "DM" in p.other(locale=en)
        assert "registered" in p.not_registered(locale=en)
