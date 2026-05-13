"""Unit tests for audit-log route helpers (Sprint 4.5-F)."""

from __future__ import annotations

from datetime import UTC
from unittest.mock import MagicMock

from starlette.datastructures import QueryParams

from pipirik_wars.admin_web.routes.audit import _parse_datetime, _parse_filters


class TestParseDatetime:
    def test_returns_none_for_empty_string(self) -> None:
        assert _parse_datetime("") is None

    def test_returns_none_for_none(self) -> None:
        assert _parse_datetime(None) is None

    def test_parses_iso_datetime(self) -> None:
        result = _parse_datetime("2026-01-15T10:30")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30
        assert result.tzinfo == UTC

    def test_parses_datetime_with_tz(self) -> None:
        result = _parse_datetime("2026-01-15T10:30:00+00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_returns_none_for_invalid(self) -> None:
        assert _parse_datetime("not-a-date") is None

    def test_returns_none_for_partial_date(self) -> None:
        result = _parse_datetime("2026-13-01")
        assert result is None


class TestParseFilters:
    def _make_request(self, params: dict[str, str] | None = None) -> MagicMock:
        request = MagicMock()
        request.query_params = QueryParams(params or {})
        return request

    def test_defaults(self) -> None:
        request = self._make_request()
        f = _parse_filters(request)
        assert f.page == 1
        assert f.log_type == "all"
        assert f.date_from is None
        assert f.date_to is None
        assert f.actor_id is None
        assert f.action is None
        assert f.source is None

    def test_parses_page(self) -> None:
        request = self._make_request({"page": "3"})
        f = _parse_filters(request)
        assert f.page == 3

    def test_invalid_page_defaults_to_1(self) -> None:
        request = self._make_request({"page": "abc"})
        f = _parse_filters(request)
        assert f.page == 1

    def test_parses_source(self) -> None:
        request = self._make_request({"source": "bot"})
        f = _parse_filters(request)
        assert f.source == "bot"

    def test_parses_log_type(self) -> None:
        request = self._make_request({"log_type": "admin"})
        f = _parse_filters(request)
        assert f.log_type == "admin"

    def test_parses_action(self) -> None:
        request = self._make_request({"action": "length_grant"})
        f = _parse_filters(request)
        assert f.action == "length_grant"

    def test_empty_actor_id_becomes_none(self) -> None:
        request = self._make_request({"actor_id": ""})
        f = _parse_filters(request)
        assert f.actor_id is None

    def test_parses_dates(self) -> None:
        request = self._make_request(
            {
                "date_from": "2026-01-01T00:00",
                "date_to": "2026-12-31T23:59",
            }
        )
        f = _parse_filters(request)
        assert f.date_from is not None
        assert f.date_to is not None
        assert f.date_from.year == 2026
        assert f.date_to.month == 12
