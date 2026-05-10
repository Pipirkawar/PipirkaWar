"""Юнит-тесты `OraclePresenter` (Спринт 1.4.B → 1.5.D → 3.6-B; ПД 1.4.4, ГДД §11.1).

Покрываем:

1. **chat-ветки** (`group`/`other`/`not_registered`) — что вызывают
   правильные ключи `oracle-*`.
2. **`success`** — подстановка `{user}` в шаблон + параметры
   `base_cm`/`tribe_bonus_cm`/`n_active_tribes`/`new_length_cm`/`prediction`,
   композиция строк (3.6-B): `oracle-success-prediction` + `oracle-base-line`
   + опц. `oracle-tribe-bonus-line` + опц. `oracle-total-line` +
   `oracle-new-length-line`. Строка-за-племена и итог скрываются при
   `n_active_tribes == 0`.
3. **`already_used`** — расчёт часов/минут до 00:00 МСК.
4. Интеграция с `FluentMessageBundle`: проверяем человекочитаемый
   текст для RU/EN, включая Fluent-плюрал-формы (`1 племя` /
   `2 племени` / `5 племён` для RU; `1 tribe` / `2 tribes` для EN).
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

    def test_success_no_tribes_renders_prediction_base_and_new_length(self) -> None:
        # Без бонуса-за-племена презентер шлёт три ключа:
        # oracle-success-prediction → oracle-base-line → oracle-new-length-line.
        # Строки `tribe-bonus` и `total` скрыты (т.к. base == total).
        out = self._make().success(
            template_text="Сегодня всё хорошо, {user}!",
            base_cm=7,
            tribe_bonus_cm=0,
            n_active_tribes=0,
            new_length_cm=37,
            user_display="Алиса",
            locale=Locale("ru"),
        )
        # FakeMessageBundle сериализует params в `[k=v,...]`. Шаблон
        # уже должен быть с подменённым `{user}` на «Алиса».
        assert "ru:oracle-success-prediction[prediction=Сегодня всё хорошо, Алиса!]" in out
        assert "ru:oracle-base-line[base_cm=7]" in out
        assert "ru:oracle-new-length-line[new_length_cm=37]" in out
        # Бонус-за-племена и итоговая строка отсутствуют.
        assert "oracle-tribe-bonus-line" not in out
        assert "oracle-total-line" not in out

    def test_success_with_tribes_renders_all_five_lines(self) -> None:
        out = self._make().success(
            template_text="Привет, {user}!",
            base_cm=10,
            tribe_bonus_cm=2,
            n_active_tribes=2,
            new_length_cm=42,
            user_display="Алиса",
            locale=Locale("ru"),
        )
        # Все пять блоков должны присутствовать.
        assert "ru:oracle-success-prediction[prediction=Привет, Алиса!]" in out
        assert "ru:oracle-base-line[base_cm=10]" in out
        assert "ru:oracle-tribe-bonus-line[n_active_tribes=2,tribe_bonus_cm=2]" in out
        assert "ru:oracle-total-line[total_cm=12]" in out
        assert "ru:oracle-new-length-line[new_length_cm=42]" in out

    def test_success_with_single_tribe_passes_n_active_tribes_one(self) -> None:
        # Кейс плюрала: 1 племя — Fluent сам выберет [one]/[*other] в
        # FluentMessageBundle, FakeMessageBundle просто эхит параметры.
        out = self._make().success(
            template_text="Hi, {user}!",
            base_cm=5,
            tribe_bonus_cm=1,
            n_active_tribes=1,
            new_length_cm=16,
            user_display="Bob",
            locale=Locale("en"),
        )
        assert "en:oracle-tribe-bonus-line[n_active_tribes=1,tribe_bonus_cm=1]" in out
        assert "en:oracle-total-line[total_cm=6]" in out

    def test_success_at_cap_passes_full_tribe_bonus_cm(self) -> None:
        # Cap 131: проверяем, что презентер просто пробрасывает значения,
        # клампинг — задача use-case-а.
        out = self._make().success(
            template_text="Topcase, {user}!",
            base_cm=20,
            tribe_bonus_cm=131,
            n_active_tribes=200,
            new_length_cm=200,
            user_display="Алиса",
            locale=Locale("ru"),
        )
        assert "ru:oracle-tribe-bonus-line[n_active_tribes=200,tribe_bonus_cm=131]" in out
        assert "ru:oracle-total-line[total_cm=151]" in out
        assert "ru:oracle-new-length-line[new_length_cm=200]" in out

    def test_success_template_without_placeholder_passthrough(self) -> None:
        out = self._make().success(
            template_text="Просто предсказание без имени.",
            base_cm=1,
            tribe_bonus_cm=0,
            n_active_tribes=0,
            new_length_cm=11,
            user_display="Боб",
            locale=Locale("ru"),
        )
        assert "prediction=Просто предсказание без имени." in out

    def test_success_unknown_placeholder_kept_as_is(self) -> None:
        # `{stranger}` — не наш плейсхолдер; не падаем с KeyError.
        out = self._make().success(
            template_text="Hello {stranger}",
            base_cm=2,
            tribe_bonus_cm=0,
            n_active_tribes=0,
            new_length_cm=12,
            user_display="Боб",
            locale=Locale("ru"),
        )
        assert "{stranger}" in out

    def test_success_zero_tribe_bonus_with_nonzero_n_still_renders_tribe_line(self) -> None:
        # Защитный кейс: даже если по какой-то причине `tribe_bonus_cm == 0`,
        # но `n_active_tribes > 0` — строки tribe/total всё равно показываем
        # (это решение принимает use-case, презентер просто отображает).
        out = self._make().success(
            template_text="Edge, {user}",
            base_cm=5,
            tribe_bonus_cm=0,
            n_active_tribes=3,
            new_length_cm=15,
            user_display="Боб",
            locale=Locale("ru"),
        )
        assert "ru:oracle-tribe-bonus-line[n_active_tribes=3,tribe_bonus_cm=0]" in out
        assert "ru:oracle-total-line[total_cm=5]" in out

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

    def test_success_ru_no_tribes_includes_base_only(self) -> None:
        text = self._make().success(
            template_text="Сегодня всё хорошо, {user}!",
            base_cm=7,
            tribe_bonus_cm=0,
            n_active_tribes=0,
            new_length_cm=37,
            user_display="Алиса",
            locale=Locale("ru"),
        )
        assert "Сегодня всё хорошо, Алиса!" in text
        assert "+7 см — базовая" in text
        assert "Теперь у тебя: 37 см" in text
        # Tribe-bonus и Total строки скрыты (n_active_tribes == 0).
        assert "за племена" not in text
        assert "Итого" not in text

    def test_success_en_no_tribes_includes_base_only(self) -> None:
        text = self._make().success(
            template_text="Today is great, {user}!",
            base_cm=3,
            tribe_bonus_cm=0,
            n_active_tribes=0,
            new_length_cm=15,
            user_display="Alice",
            locale=Locale("en"),
        )
        assert "Today is great, Alice!" in text
        assert "+3 cm — base" in text
        assert "Now you have: 15 cm" in text
        assert "tribe bonus" not in text
        assert "Total" not in text

    def test_success_ru_one_tribe_uses_singular_plural_form(self) -> None:
        # CLDR RU: 1 → племя
        text = self._make().success(
            template_text="Hi, {user}!",
            base_cm=10,
            tribe_bonus_cm=1,
            n_active_tribes=1,
            new_length_cm=21,
            user_display="Алиса",
            locale=Locale("ru"),
        )
        assert "+10 см — базовая" in text
        assert "+1 см — за племена (1 племя)" in text
        assert "Итого: +11 см" in text
        assert "Теперь у тебя: 21 см" in text

    def test_success_ru_two_tribes_uses_few_plural_form(self) -> None:
        # CLDR RU: 2..4 → племени
        text = self._make().success(
            template_text="Hi, {user}!",
            base_cm=10,
            tribe_bonus_cm=2,
            n_active_tribes=2,
            new_length_cm=22,
            user_display="Алиса",
            locale=Locale("ru"),
        )
        assert "+2 см — за племена (2 племени)" in text
        assert "Итого: +12 см" in text

    def test_success_ru_five_tribes_uses_other_plural_form(self) -> None:
        # CLDR RU: 5..20 → племён
        text = self._make().success(
            template_text="Hi, {user}!",
            base_cm=10,
            tribe_bonus_cm=5,
            n_active_tribes=5,
            new_length_cm=25,
            user_display="Алиса",
            locale=Locale("ru"),
        )
        assert "+5 см — за племена (5 племён)" in text
        assert "Итого: +15 см" in text

    def test_success_ru_at_cap_renders_total_151(self) -> None:
        # Кап anti-cheat = +131 см: base=20 + tribe_bonus=131 → total=151.
        text = self._make().success(
            template_text="Topcase, {user}!",
            base_cm=20,
            tribe_bonus_cm=131,
            n_active_tribes=200,
            new_length_cm=200,
            user_display="Алиса",
            locale=Locale("ru"),
        )
        assert "+20 см — базовая" in text
        assert "+131 см — за племена (200 племён)" in text
        assert "Итого: +151 см" in text
        assert "Теперь у тебя: 200 см" in text

    def test_success_en_one_tribe_uses_singular_plural_form(self) -> None:
        text = self._make().success(
            template_text="Hi, {user}!",
            base_cm=10,
            tribe_bonus_cm=1,
            n_active_tribes=1,
            new_length_cm=21,
            user_display="Bob",
            locale=Locale("en"),
        )
        assert "+10 cm — base" in text
        assert "+1 cm — tribe bonus (1 tribe)" in text
        assert "Total: +11 cm" in text
        assert "Now you have: 21 cm" in text

    def test_success_en_multiple_tribes_uses_other_plural_form(self) -> None:
        # CLDR EN: 1 → tribe, otherwise → tribes (нет [few]).
        text = self._make().success(
            template_text="Hi, {user}!",
            base_cm=10,
            tribe_bonus_cm=5,
            n_active_tribes=5,
            new_length_cm=25,
            user_display="Bob",
            locale=Locale("en"),
        )
        assert "+5 cm — tribe bonus (5 tribes)" in text
        assert "Total: +15 cm" in text

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
