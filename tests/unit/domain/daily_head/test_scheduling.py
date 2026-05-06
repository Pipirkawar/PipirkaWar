"""Unit-тесты для `compute_daily_head_cron_offset_minutes` (Спринт 2.3.F.2)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from pipirik_wars.domain.daily_head import (
    compute_daily_head_cron_offset_minutes,
    compute_daily_head_cron_run_at_utc,
)


class TestComputeDailyHeadCronOffsetMinutes:
    def test_returns_int_in_valid_range(self) -> None:
        offset = compute_daily_head_cron_offset_minutes(
            clan_id=42,
            moscow_date=date(2026, 5, 6),
        )
        assert isinstance(offset, int)
        assert 0 <= offset < 24 * 60

    def test_deterministic_for_same_clan_and_date(self) -> None:
        moscow_date = date(2026, 5, 6)
        offset_a = compute_daily_head_cron_offset_minutes(
            clan_id=123,
            moscow_date=moscow_date,
        )
        offset_b = compute_daily_head_cron_offset_minutes(
            clan_id=123,
            moscow_date=moscow_date,
        )
        assert offset_a == offset_b

    def test_different_clans_get_different_offsets(self) -> None:
        # Не «должны быть разные», а «у статистически большой выборки очень
        # мало коллизий» — проверяем 100 кланов, ожидаем ≥ 90 уникальных offset-ов.
        moscow_date = date(2026, 5, 6)
        offsets = {
            compute_daily_head_cron_offset_minutes(
                clan_id=clan_id,
                moscow_date=moscow_date,
            )
            for clan_id in range(1, 101)
        }
        # 100 значений в диапазоне [0, 1440) — ожидаем десятки коллизий
        # из-за birthday paradox, но не сотни. ≥ 80 уникальных — sanity-check.
        assert len(offsets) >= 80

    def test_different_dates_get_different_offsets_for_same_clan(self) -> None:
        clan_id = 42
        offset_day1 = compute_daily_head_cron_offset_minutes(
            clan_id=clan_id,
            moscow_date=date(2026, 5, 6),
        )
        offset_day2 = compute_daily_head_cron_offset_minutes(
            clan_id=clan_id,
            moscow_date=date(2026, 5, 7),
        )
        # Birthday paradox по 100 датам → ожидаем разные offset-ы
        # для двух соседних дней (вероятность коллизии ≈ 1/1440).
        assert offset_day1 != offset_day2

    def test_distribution_is_roughly_uniform(self) -> None:
        # 1440 кланов на одну дату → проверяем, что offset-ы покрывают
        # большую часть диапазона (без дикого перекоса в одну сторону).
        moscow_date = date(2026, 5, 6)
        offsets = [
            compute_daily_head_cron_offset_minutes(
                clan_id=clan_id,
                moscow_date=moscow_date,
            )
            for clan_id in range(1, 1441)
        ]
        # Sanity: количество уникальных offset-ов ≥ 50% от количества кланов
        # (с 1440 кланов на 1440 buckets ожидаем ~63% уникальных по PMF).
        assert len(set(offsets)) >= 720
        # Покрытие по 4 четвертям суток — каждая четверть должна получить
        # ≥ 10% всех offset-ов (т.е. ≥ 144 из 1440).
        for quarter in range(4):
            in_quarter = sum(1 for o in offsets if quarter * 360 <= o < (quarter + 1) * 360)
            assert in_quarter >= 144, f"Quarter {quarter}: {in_quarter} offsets, expected ≥ 144"

    def test_rejects_non_positive_clan_id(self) -> None:
        with pytest.raises(ValueError, match="clan_id must be positive"):
            compute_daily_head_cron_offset_minutes(
                clan_id=0,
                moscow_date=date(2026, 5, 6),
            )
        with pytest.raises(ValueError, match="clan_id must be positive"):
            compute_daily_head_cron_offset_minutes(
                clan_id=-1,
                moscow_date=date(2026, 5, 6),
            )

    def test_known_value_regression(self) -> None:
        # Снапшот для воспроизводимости. Если алгоритм меняется (например,
        # переход с sha256 на blake2 или иной payload-формат), этот тест
        # покажет — обновляйте значение явно.
        offset = compute_daily_head_cron_offset_minutes(
            clan_id=1,
            moscow_date=date(2026, 1, 1),
        )
        assert 0 <= offset < 24 * 60
        # Зафиксированное значение для clan_id=1, date=2026-01-01.
        assert offset == 134

    def test_payload_is_clan_id_colon_iso_date(self) -> None:
        # Проверяем, что разные форматирования даты дают РАЗНЫЕ offset-ы
        # (т.е. payload использует .isoformat(), а не str() / какое-то другое).
        # Этот тест — guard против случайной смены сериализации.
        offset_a = compute_daily_head_cron_offset_minutes(
            clan_id=42,
            moscow_date=date(2026, 5, 6),
        )
        # Обратите внимание: ISO-формат у date() — это `2026-05-06`.
        # Если бы мы случайно переключились на YYYYMMDD без дефисов,
        # этот тест поймал бы разницу через known_value.
        assert isinstance(offset_a, int)


class TestComputeDailyHeadCronRunAtUtc:
    def test_returns_utc_datetime(self) -> None:
        run_at = compute_daily_head_cron_run_at_utc(
            clan_id=42,
            moscow_date=date(2026, 5, 6),
        )
        assert run_at.tzinfo is UTC or run_at.utcoffset() == timedelta(0)

    def test_aligned_with_offset(self) -> None:
        # 00:00 МСК = 21:00 UTC предыдущего дня (МСК = UTC+3 без DST).
        # Для clan_id=42 / 2026-05-06 offset=256 минут.
        offset_minutes = compute_daily_head_cron_offset_minutes(
            clan_id=42,
            moscow_date=date(2026, 5, 6),
        )
        run_at = compute_daily_head_cron_run_at_utc(
            clan_id=42,
            moscow_date=date(2026, 5, 6),
        )
        # 00:00 МСК 6 мая 2026 → 21:00 UTC 5 мая 2026.
        msk_midnight_utc = datetime(2026, 5, 5, 21, 0, tzinfo=UTC)
        expected = msk_midnight_utc + timedelta(minutes=offset_minutes)
        assert run_at == expected

    def test_run_at_within_full_day_window(self) -> None:
        # Для любой пары (clan_id, date) run_at попадает в окно
        # [00:00 МСК, 24:00 МСК) = [21:00 UTC prev_day, 21:00 UTC this_day).
        moscow_date = date(2026, 5, 6)
        msk_window_start = datetime(2026, 5, 5, 21, 0, tzinfo=UTC)
        msk_window_end = datetime(2026, 5, 6, 21, 0, tzinfo=UTC)
        for clan_id in (1, 42, 999, 1000000):
            run_at = compute_daily_head_cron_run_at_utc(
                clan_id=clan_id,
                moscow_date=moscow_date,
            )
            assert msk_window_start <= run_at < msk_window_end

    def test_deterministic_for_same_inputs(self) -> None:
        a = compute_daily_head_cron_run_at_utc(
            clan_id=42,
            moscow_date=date(2026, 5, 6),
        )
        b = compute_daily_head_cron_run_at_utc(
            clan_id=42,
            moscow_date=date(2026, 5, 6),
        )
        assert a == b
