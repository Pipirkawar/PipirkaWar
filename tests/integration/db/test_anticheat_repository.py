"""Integration-тесты `SqlAlchemyAnticheatRepository` (Спринт 1.6.C)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.shared.ports import AuditAction, AuditEntry, AuditSource
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyAnticheatRepository
from pipirik_wars.infrastructure.db.services import SqlAlchemyAuditLogger
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

_NOW = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
_ORGANIC_SOURCES: tuple[AuditSource, ...] = (
    AuditSource.FOREST,
    AuditSource.ORACLE,
    AuditSource.REFERRAL_SIGNUP,
    AuditSource.REFERRAL_THICKNESS,
    AuditSource.PVP_REWARD,
    AuditSource.CARAVAN_REWARD,
    AuditSource.RAID_REWARD,
    AuditSource.ADMIN_GRANT,
)


def _entry(
    *,
    action: AuditAction = AuditAction.LENGTH_GRANT,
    target_id: str,
    delta_cm: int | None,
    occurred_at: datetime,
    source: AuditSource,
    target_kind: str = "player",
) -> AuditEntry:
    """Минимальная фабрика AuditEntry для аггрегационных тестов."""
    return AuditEntry(
        action=action,
        actor_id=None,
        target_kind=target_kind,
        target_id=target_id,
        before=None,
        after=None,
        reason="test",
        idempotency_key=None,
        occurred_at=occurred_at,
        source=source,
        clamped_from=None,
        delta_cm=delta_cm,
    )


class TestSumOrganicInWindow:
    @pytest.mark.asyncio
    async def test_empty_audit_log_returns_zero(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(days=1),
                organic_sources=_ORGANIC_SOURCES,
            )
        assert window.player_id == 42
        assert window.organic_sum_cm == 0

    @pytest.mark.asyncio
    async def test_sums_organic_positive_deltas(self, uow: SqlAlchemyUnitOfWork) -> None:
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=5,
                    occurred_at=_NOW - timedelta(hours=2),
                    source=AuditSource.FOREST,
                )
            )
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=10,
                    occurred_at=_NOW - timedelta(hours=1),
                    source=AuditSource.ORACLE,
                )
            )
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=2,
                    occurred_at=_NOW - timedelta(minutes=30),
                    source=AuditSource.ADMIN_GRANT,
                )
            )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(hours=24),
                organic_sources=_ORGANIC_SOURCES,
            )
        assert window.organic_sum_cm == 17

    @pytest.mark.asyncio
    async def test_excludes_donate_sources(self, uow: SqlAlchemyUnitOfWork) -> None:
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=5,
                    occurred_at=_NOW - timedelta(hours=1),
                    source=AuditSource.FOREST,
                )
            )
            for donate in (
                AuditSource.STARS_PAYMENT,
                AuditSource.TON_PAYMENT,
                AuditSource.USDT_PAYMENT,
            ):
                await logger.record(
                    _entry(
                        target_id="42",
                        delta_cm=1000,
                        occurred_at=_NOW - timedelta(hours=2),
                        source=donate,
                    )
                )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(hours=24),
                organic_sources=_ORGANIC_SOURCES,
            )
        # Только organic FOREST=5; 3×1000 от донат-источников игнорируются.
        assert window.organic_sum_cm == 5

    @pytest.mark.asyncio
    async def test_excludes_admin_refund_negative_delta(self, uow: SqlAlchemyUnitOfWork) -> None:
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=10,
                    occurred_at=_NOW - timedelta(hours=2),
                    source=AuditSource.FOREST,
                )
            )
            # admin_refund: отрицательная дельта, источник вне organic-whitelist.
            await logger.record(
                _entry(
                    action=AuditAction.LENGTH_REVOKE,
                    target_id="42",
                    delta_cm=-3,
                    occurred_at=_NOW - timedelta(hours=1),
                    source=AuditSource.ADMIN_REFUND,
                )
            )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(hours=24),
                organic_sources=_ORGANIC_SOURCES,
            )
        # admin_refund фильтруется и по source, и по `delta_cm > 0`.
        assert window.organic_sum_cm == 10

    @pytest.mark.asyncio
    async def test_excludes_unknown_source(self, uow: SqlAlchemyUnitOfWork) -> None:
        """`unknown` (backfill из 1.6.A) не в organic-list — не суммируется."""
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=10,
                    occurred_at=_NOW - timedelta(hours=1),
                    source=AuditSource.FOREST,
                )
            )
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=1000,
                    occurred_at=_NOW - timedelta(hours=2),
                    source=AuditSource.UNKNOWN,
                )
            )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(hours=24),
                organic_sources=_ORGANIC_SOURCES,
            )
        assert window.organic_sum_cm == 10

    @pytest.mark.asyncio
    async def test_window_cutoff_excludes_old_events(self, uow: SqlAlchemyUnitOfWork) -> None:
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            # 25 часов назад — за окном 24h
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=999,
                    occurred_at=_NOW - timedelta(hours=25),
                    source=AuditSource.FOREST,
                )
            )
            # 1 час назад — внутри окна 24h
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=10,
                    occurred_at=_NOW - timedelta(hours=1),
                    source=AuditSource.FOREST,
                )
            )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(hours=24),
                organic_sources=_ORGANIC_SOURCES,
            )
        assert window.organic_sum_cm == 10

    @pytest.mark.asyncio
    async def test_since_boundary_inclusive(self, uow: SqlAlchemyUnitOfWork) -> None:
        """`occurred_at == since` должен включаться (>= boundary)."""
        since = _NOW - timedelta(hours=24)
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=7,
                    occurred_at=since,
                    source=AuditSource.FOREST,
                )
            )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=since,
                organic_sources=_ORGANIC_SOURCES,
            )
        assert window.organic_sum_cm == 7

    @pytest.mark.asyncio
    async def test_excludes_other_player(self, uow: SqlAlchemyUnitOfWork) -> None:
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=10,
                    occurred_at=_NOW - timedelta(hours=1),
                    source=AuditSource.FOREST,
                )
            )
            await logger.record(
                _entry(
                    target_id="999",  # другой игрок
                    delta_cm=1000,
                    occurred_at=_NOW - timedelta(hours=1),
                    source=AuditSource.FOREST,
                )
            )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(hours=24),
                organic_sources=_ORGANIC_SOURCES,
            )
        assert window.organic_sum_cm == 10

    @pytest.mark.asyncio
    async def test_excludes_null_delta_cm(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Старые записи без `delta_cm` (например, до 1.6.D) не суммируются."""
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=None,  # явно NULL
                    occurred_at=_NOW - timedelta(hours=1),
                    source=AuditSource.FOREST,
                )
            )
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=5,
                    occurred_at=_NOW - timedelta(hours=2),
                    source=AuditSource.FOREST,
                )
            )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(hours=24),
                organic_sources=_ORGANIC_SOURCES,
            )
        assert window.organic_sum_cm == 5

    @pytest.mark.asyncio
    async def test_excludes_zero_delta_cm(self, uow: SqlAlchemyUnitOfWork) -> None:
        """`delta_cm = 0` — не положительная дельта, не учитывается."""
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=0,
                    occurred_at=_NOW - timedelta(hours=1),
                    source=AuditSource.FOREST,
                )
            )
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=3,
                    occurred_at=_NOW - timedelta(hours=2),
                    source=AuditSource.FOREST,
                )
            )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(hours=24),
                organic_sources=_ORGANIC_SOURCES,
            )
        assert window.organic_sum_cm == 3

    @pytest.mark.asyncio
    async def test_target_kind_other_excluded(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Записи с `target_kind != 'player'` не учитываются (clan-аудит и т.п.)."""
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=999,
                    occurred_at=_NOW - timedelta(hours=1),
                    source=AuditSource.FOREST,
                    target_kind="clan",
                )
            )
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=5,
                    occurred_at=_NOW - timedelta(hours=2),
                    source=AuditSource.FOREST,
                )
            )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(hours=24),
                organic_sources=_ORGANIC_SOURCES,
            )
        assert window.organic_sum_cm == 5

    @pytest.mark.asyncio
    async def test_partial_organic_subset(self, uow: SqlAlchemyUnitOfWork) -> None:
        """`organic_sources` — фильтр; не-в-списке источники игнорируются."""
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=10,
                    occurred_at=_NOW - timedelta(hours=1),
                    source=AuditSource.FOREST,
                )
            )
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=20,
                    occurred_at=_NOW - timedelta(hours=2),
                    source=AuditSource.ORACLE,
                )
            )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            # Только FOREST в списке — ORACLE-запись 20 см игнорируется.
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(hours=24),
                organic_sources=(AuditSource.FOREST,),
            )
        assert window.organic_sum_cm == 10

    @pytest.mark.asyncio
    async def test_empty_organic_sources_returns_zero(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(hours=24),
                organic_sources=(),
            )
        assert window.organic_sum_cm == 0

    @pytest.mark.asyncio
    async def test_naive_since_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyAnticheatRepository(uow=uow)
        with pytest.raises(ValueError, match="must be timezone-aware"):
            await repo.sum_organic_in_window(
                player_id=42,
                since=datetime(2026, 5, 5, 12, 0, 0),  # naive
                organic_sources=_ORGANIC_SOURCES,
            )

    @pytest.mark.asyncio
    async def test_zero_player_id_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyAnticheatRepository(uow=uow)
        with pytest.raises(ValueError, match="player_id must be > 0"):
            await repo.sum_organic_in_window(
                player_id=0,
                since=_NOW - timedelta(hours=24),
                organic_sources=_ORGANIC_SOURCES,
            )

    @pytest.mark.asyncio
    async def test_excludes_oracle_tribe_bonus_source(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Спринт 3.6-A: `oracle_tribe_bonus` пишется в audit_log, но не входит
        в `organic_sources` → не учитывается в rolling-окне 24h/7d. Это
        защищает крупные племена от «съедания» хардкапа своих участников."""
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            # Базовая oracle-проводка попадает в organic-окно.
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=10,
                    occurred_at=_NOW - timedelta(hours=2),
                    source=AuditSource.ORACLE,
                )
            )
            # Tribe-bonus поверх — отдельный source, audit-only.
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=131,
                    occurred_at=_NOW - timedelta(hours=2),
                    source=AuditSource.ORACLE_TRIBE_BONUS,
                )
            )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(hours=24),
                organic_sources=_ORGANIC_SOURCES,
            )
        # Только базовая oracle-проводка (10 см) — tribe-bonus 131 см
        # игнорируется, потому что `ORACLE_TRIBE_BONUS` не в whitelist-е.
        assert window.organic_sum_cm == 10

    @pytest.mark.asyncio
    async def test_weekly_window_aggregation(self, uow: SqlAlchemyUnitOfWork) -> None:
        """7-day rolling-window — агрегирует все organic-события за неделю."""
        logger = SqlAlchemyAuditLogger(uow=uow)
        async with uow:
            for hours_ago in (1, 24, 72, 144, 168):  # 168h == 7d boundary
                await logger.record(
                    _entry(
                        target_id="42",
                        delta_cm=1000,
                        occurred_at=_NOW - timedelta(hours=hours_ago),
                        source=AuditSource.FOREST,
                    )
                )
            # 169 часов назад — за окном
            await logger.record(
                _entry(
                    target_id="42",
                    delta_cm=999,
                    occurred_at=_NOW - timedelta(hours=169),
                    source=AuditSource.FOREST,
                )
            )

        repo = SqlAlchemyAnticheatRepository(uow=uow)
        async with uow:
            window = await repo.sum_organic_in_window(
                player_id=42,
                since=_NOW - timedelta(days=7),
                organic_sources=_ORGANIC_SOURCES,
            )
        # 5 событий по 1000 см внутри 7-дневного окна.
        assert window.organic_sum_cm == 5000
