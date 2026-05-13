"""Unit-тесты rate-limiter (Sprint 4.5-H)."""

from __future__ import annotations

from unittest import mock

from pipirik_wars.admin_web.auth.rate_limit import RateLimitMiddleware, _SlidingWindow


class TestSlidingWindow:
    def test_single_hit(self) -> None:
        w = _SlidingWindow(60.0)
        assert w.hit(100.0) == 1

    def test_multiple_hits_within_window(self) -> None:
        w = _SlidingWindow(60.0)
        for i in range(5):
            count = w.hit(100.0 + i)
        assert count == 5

    def test_old_hits_expire(self) -> None:
        w = _SlidingWindow(10.0)
        w.hit(100.0)
        w.hit(105.0)
        # At t=111, cutoff=101 → hit@100 expired, hit@105 alive + new hit = 2
        assert w.hit(111.0) == 2

    def test_all_hits_expire(self) -> None:
        w = _SlidingWindow(10.0)
        w.hit(1.0)
        w.hit(2.0)
        assert w.hit(100.0) == 1

    def test_current_count_without_adding(self) -> None:
        w = _SlidingWindow(10.0)
        w.hit(1.0)
        w.hit(2.0)
        assert w.current_count(5.0) == 2
        assert w.current_count(15.0) == 0


class TestRateLimitMiddlewareInit:
    def test_default_paths(self) -> None:
        app_mock = mock.MagicMock()
        mw = RateLimitMiddleware(app_mock)
        assert "/auth/telegram/callback" in mw._rate_limit_paths
        assert "/totp/verify" in mw._rate_limit_paths
        assert "/totp/setup" in mw._rate_limit_paths

    def test_custom_paths(self) -> None:
        app_mock = mock.MagicMock()
        custom = frozenset({"/custom"})
        mw = RateLimitMiddleware(app_mock, rate_limit_paths=custom)
        assert mw._rate_limit_paths == custom

    def test_custom_limits(self) -> None:
        app_mock = mock.MagicMock()
        mw = RateLimitMiddleware(app_mock, max_requests=5, window_seconds=30)
        assert mw._max_requests == 5
        assert mw._window_seconds == 30


class TestRateLimitGetClientIp:
    def test_with_client(self) -> None:
        app_mock = mock.MagicMock()
        mw = RateLimitMiddleware(app_mock)
        request = mock.MagicMock()
        request.client.host = "1.2.3.4"
        assert mw._get_client_ip(request) == "1.2.3.4"

    def test_no_client(self) -> None:
        app_mock = mock.MagicMock()
        mw = RateLimitMiddleware(app_mock)
        request = mock.MagicMock()
        request.client = None
        assert mw._get_client_ip(request) == "0.0.0.0"
