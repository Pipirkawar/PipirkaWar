"""Unit-тесты презентеров `/oracle` (Спринт 1.4.B)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from pipirik_wars.bot.presenters.oracle import (
    REPLY_GROUP_RU,
    REPLY_NOT_REGISTERED_RU,
    REPLY_OTHER_RU,
    render_oracle_already_used,
    render_oracle_success,
)


class TestRenderOracleSuccess:
    def test_renders_user_placeholder(self) -> None:
        out = render_oracle_success(
            template_text="Сегодня всё хорошо, {user}!",
            bonus_cm=7,
            new_length_cm=37,
            user_display="Алиса",
        )
        assert "Алиса" in out
        assert "+7 см" in out
        assert "37 см" in out

    def test_template_without_placeholder_passthrough(self) -> None:
        out = render_oracle_success(
            template_text="Просто предсказание без имени.",
            bonus_cm=1,
            new_length_cm=11,
            user_display="Боб",
        )
        assert "Просто предсказание" in out
        assert "+1 см" in out

    def test_unknown_placeholder_kept_as_is(self) -> None:
        out = render_oracle_success(
            template_text="Hello {stranger}",
            bonus_cm=2,
            new_length_cm=12,
            user_display="Боб",
        )
        # Должен сохранить `{stranger}` без падения с KeyError.
        assert "{stranger}" in out


class TestRenderOracleAlreadyUsed:
    def test_includes_hours_and_minutes_until_reset(self) -> None:
        moscow_now = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)  # 15:00 МСК
        out = render_oracle_already_used(
            moscow_date=date(2026, 5, 5),
            now=moscow_now,
        )
        # До 00:00 МСК следующего дня (= 21:00 UTC) осталось 9 часов.
        assert "9ч" in out
        assert "00:00" in out

    def test_zero_when_already_past_reset(self) -> None:
        # `now` уже за полночью МСК, но moscow_date — вчера; не валидно
        # в реальной игре, но defensive check.
        out = render_oracle_already_used(
            moscow_date=date(2026, 5, 5),
            now=datetime(2026, 5, 5, 23, 0, tzinfo=UTC),  # 02:00 МСК следующего дня
        )
        assert "0ч 00м" in out


def test_static_messages_are_non_empty() -> None:
    assert REPLY_GROUP_RU
    assert REPLY_OTHER_RU
    assert REPLY_NOT_REGISTERED_RU
    # Все три должны быть разные — иначе зачем отдельные константы.
    assert len({REPLY_GROUP_RU, REPLY_OTHER_RU, REPLY_NOT_REGISTERED_RU}) == 3
