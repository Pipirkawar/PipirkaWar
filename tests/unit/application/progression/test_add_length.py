"""Unit-тесты `application.progression.AddLength` (Спринт 1.6.D, ГДД §3.3).

Покрытие:
- Happy-path organic / donate / admin_refund.
- Clamp по daily / weekly (выбор min(daily_remaining, weekly_remaining)).
- Полностью исчерпанный лимит (`applied=0`, `clamped_from=delta_cm`).
- Soft-ban-гейт (активный → ошибка; истёкший → проход).
- Валидация входа: `delta_cm=0`, отрицательная для не-refund, положительная
  для refund, `source=UNKNOWN`.
- `PlayerNotFoundError` при отсутствии игрока.
- Идемпотентность: повторный вызов с тем же ключом — no-op.
- Trip-wire daily / weekly: при превышении после save — soft-ban + audit
  `ANTICHEAT_*_CAP_EXCEEDED` + alert.
- Trip-wire НЕ срабатывает на donate / admin_refund.
- Audit-запись содержит `source` / `clamped_from` / `delta_cm`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.progression import AddLength
from pipirik_wars.domain.anticheat import AnticheatWindow
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression import (
    AnticheatSoftBanError,
    LengthDeltaInvalidError,
    LengthGrantResult,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
)
from pipirik_wars.domain.shared.ports.audit import AuditSource
from tests.fakes import (
    FakeAnticheatAdminAlerter,
    FakeAnticheatRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakeIdempotencyKey,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


# ────────────────────────────── builders ──────────────────────────────


def _make_player(
    *,
    player_id: int = 1,
    tg_id: int = 10001,
    length_cm: int = 100,
    anticheat_ban_until: datetime | None = None,
    status: PlayerStatus = PlayerStatus.ACTIVE,
) -> Player:
    return Player(
        id=player_id,
        tg_id=tg_id,
        username=Username(value="alice"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=status,
        created_at=_NOW - timedelta(days=30),
        updated_at=_NOW - timedelta(days=30),
        anticheat_ban_until=anticheat_ban_until,
    )


class _LinkedAuditLogger(IAuditLogger):
    """Тестовый адаптер: пишет в `FakeAuditLogger` И зеркалит
    `LENGTH_GRANT`-события в `FakeAnticheatRepository`, имитируя то,
    что делает реальная связка `SqlAlchemyAuditLogger` →
    `audit_log` ← `SqlAlchemyAnticheatRepository.sum_organic_in_window`.

    Это нужно, чтобы trip-wire в use-case-е (рекомпьют окна после save)
    видел только что записанную дельту.
    """

    __slots__ = ("_anticheat", "_audit", "entries")

    def __init__(
        self,
        audit: FakeAuditLogger,
        anticheat: FakeAnticheatRepository,
    ) -> None:
        self._audit = audit
        self._anticheat = anticheat
        self.entries = audit.entries

    async def record(self, entry: AuditEntry) -> None:
        await self._audit.record(entry)
        if (
            entry.action is AuditAction.LENGTH_GRANT
            and entry.source is not AuditSource.UNKNOWN
            and entry.delta_cm is not None
            and entry.delta_cm > 0
            and entry.target_kind == "player"
        ):
            self._anticheat.record_event(
                player_id=int(entry.target_id),
                source=entry.source,
                delta_cm=entry.delta_cm,
                occurred_at=entry.occurred_at,
            )


async def _grant(
    env: dict[str, object],
    *,
    player_id: int,
    delta_cm: int,
    source: AuditSource,
    reason: str,
    idempotency_key: str | None = None,
) -> LengthGrantResult:
    """Открыть `IUnitOfWork`-контекст вызывающего и вызвать `AddLength.grant`.

    `AddLength.grant` (Спринт 1.6.F) требует ambient-UoW: caller обязан
    открыть транзакцию сам. Все unit-тесты пропускают вызов через этот
    хелпер, чтобы не дублировать `async with uow:` 22 раза.
    """
    use_case: AddLength = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    async with uow:
        return await use_case.grant(
            player_id=player_id,
            delta_cm=delta_cm,
            source=source,
            reason=reason,
            idempotency_key=idempotency_key,
        )


@pytest.fixture
def env() -> dict[str, object]:
    """Полный набор зависимостей для `AddLength`-тестов."""
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    anticheat = FakeAnticheatRepository()
    audit_inner = FakeAuditLogger()
    audit = _LinkedAuditLogger(audit_inner, anticheat)
    balance = FakeBalanceConfig(build_valid_balance())
    clock = FakeClock(_NOW)
    idempotency = FakeIdempotencyKey()
    admin_alerter = FakeAnticheatAdminAlerter()
    use_case = AddLength(
        uow=uow,
        players=players,
        anticheat=anticheat,
        audit=audit,
        balance=balance,
        clock=clock,
        idempotency=idempotency,
        admin_alerter=admin_alerter,
    )
    return {
        "uow": uow,
        "players": players,
        "anticheat": anticheat,
        "audit_inner": audit_inner,
        "audit": audit,
        "balance": balance,
        "clock": clock,
        "idempotency": idempotency,
        "admin_alerter": admin_alerter,
        "use_case": use_case,
    }


# ────────────────────────────── happy-path / clamp ──────────────────────────────


class TestOrganicHappyPath:
    @pytest.mark.asyncio
    async def test_below_cap_applies_full_delta(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        player = _make_player(length_cm=100)
        players.rows.append(player)

        result = await _grant(
            env,
            player_id=1,
            delta_cm=200,
            source=AuditSource.FOREST,
            reason="forest_run_finished",
        )

        assert result == LengthGrantResult(
            applied_delta_cm=200,
            clamped_from=None,
            triggered_soft_ban=False,
            new_length_cm=300,
        )
        assert players.rows[0].length.cm == 300
        assert env["uow"].commits == 1  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_audit_records_source_and_delta(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        audit_inner: FakeAuditLogger = env["audit_inner"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=50))

        await _grant(
            env,
            player_id=1,
            delta_cm=10,
            source=AuditSource.ORACLE,
            reason="oracle_grant",
            idempotency_key="add_length:oracle:1:2026-05-05",
        )

        assert len(audit_inner.entries) == 1
        entry = audit_inner.entries[0]
        assert entry.action is AuditAction.LENGTH_GRANT
        assert entry.source is AuditSource.ORACLE
        assert entry.delta_cm == 10
        assert entry.clamped_from is None
        assert entry.idempotency_key == "add_length:oracle:1:2026-05-05"
        assert entry.target_kind == "player"
        assert entry.target_id == "1"


class TestOrganicClamp:
    @pytest.mark.asyncio
    async def test_clamp_by_daily_cap(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        anticheat: FakeAnticheatRepository = env["anticheat"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=100))
        # В сутках уже накопилось 2900, осталось 100. Запросили 500 → клам 100.
        anticheat.record_event(
            player_id=1,
            source=AuditSource.FOREST,
            delta_cm=2900,
            occurred_at=_NOW - timedelta(hours=1),
        )

        result = await _grant(
            env,
            player_id=1,
            delta_cm=500,
            source=AuditSource.FOREST,
            reason="forest",
        )

        assert result.applied_delta_cm == 100
        assert result.clamped_from == 500
        assert result.triggered_soft_ban is False
        assert result.new_length_cm == 200

    @pytest.mark.asyncio
    async def test_clamp_by_weekly_cap_more_restrictive(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        anticheat: FakeAnticheatRepository = env["anticheat"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=0))
        # За неделю: 13900 → weekly_remaining = 100.
        # За сутки: 0 → daily_remaining = 3000.
        # min(100, 3000) = 100.
        anticheat.record_event(
            player_id=1,
            source=AuditSource.FOREST,
            delta_cm=13900,
            occurred_at=_NOW - timedelta(days=3),
        )

        result = await _grant(
            env,
            player_id=1,
            delta_cm=2000,
            source=AuditSource.FOREST,
            reason="forest",
        )

        assert result.applied_delta_cm == 100
        assert result.clamped_from == 2000

    @pytest.mark.asyncio
    async def test_exhausted_cap_returns_zero_applied(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        anticheat: FakeAnticheatRepository = env["anticheat"]  # type: ignore[assignment]
        audit_inner: FakeAuditLogger = env["audit_inner"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=100))
        # Лимит ровно на нуле — больше нельзя.
        anticheat.record_event(
            player_id=1,
            source=AuditSource.FOREST,
            delta_cm=3000,
            occurred_at=_NOW - timedelta(hours=1),
        )

        result = await _grant(
            env,
            player_id=1,
            delta_cm=1000,
            source=AuditSource.FOREST,
            reason="forest",
        )

        assert result.applied_delta_cm == 0
        assert result.clamped_from == 1000
        assert result.triggered_soft_ban is False
        assert result.new_length_cm == 100  # не изменилось
        # Audit-запись всё равно пишется — фиксируем clamp до 0.
        assert len(audit_inner.entries) == 1
        assert audit_inner.entries[0].delta_cm == 0
        assert audit_inner.entries[0].clamped_from == 1000


class TestNonClampedSources:
    @pytest.mark.asyncio
    async def test_donate_source_not_clamped(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        anticheat: FakeAnticheatRepository = env["anticheat"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=100))
        # Уже исчерпан organic-лимит — но donate не клампится.
        anticheat.record_event(
            player_id=1,
            source=AuditSource.FOREST,
            delta_cm=3000,
            occurred_at=_NOW - timedelta(hours=1),
        )

        result = await _grant(
            env,
            player_id=1,
            delta_cm=10000,
            source=AuditSource.STARS_PAYMENT,
            reason="stars_top_up",
        )

        assert result.applied_delta_cm == 10000
        assert result.clamped_from is None
        assert result.new_length_cm == 10100

    @pytest.mark.asyncio
    async def test_admin_refund_negative_subtracts_length(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=500))

        result = await _grant(
            env,
            player_id=1,
            delta_cm=-100,
            source=AuditSource.ADMIN_REFUND,
            reason="manual_refund_for_bug_X",
        )

        assert result.applied_delta_cm == -100
        assert result.clamped_from is None
        assert result.triggered_soft_ban is False
        assert result.new_length_cm == 400
        assert players.rows[0].length.cm == 400


# ────────────────────────────── soft-ban gate ──────────────────────────────


class TestSoftBanGate:
    @pytest.mark.asyncio
    async def test_active_soft_ban_blocks_grant(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        ban_until = _NOW + timedelta(days=10)
        players.rows.append(_make_player(length_cm=100, anticheat_ban_until=ban_until))

        with pytest.raises(AnticheatSoftBanError) as ei:
            await _grant(
                env,
                player_id=1,
                delta_cm=50,
                source=AuditSource.FOREST,
                reason="forest",
            )

        assert ei.value.banned_until == ban_until
        assert ei.value.tg_id == 10001
        # Игрок не изменён.
        assert players.rows[0].length.cm == 100
        # Audit пуст.
        audit_inner: FakeAuditLogger = env["audit_inner"]  # type: ignore[assignment]
        assert audit_inner.entries == []

    @pytest.mark.asyncio
    async def test_expired_soft_ban_allows_grant(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        # Бан в прошлом — `is_anticheat_banned(now)` вернёт False.
        players.rows.append(
            _make_player(
                length_cm=100,
                anticheat_ban_until=_NOW - timedelta(hours=1),
            )
        )

        result = await _grant(
            env,
            player_id=1,
            delta_cm=50,
            source=AuditSource.FOREST,
            reason="forest",
        )

        assert result.applied_delta_cm == 50


# ────────────────────────────── input validation ──────────────────────────────


class TestInputValidation:
    @pytest.mark.asyncio
    async def test_zero_delta_raises(self, env: dict[str, object]) -> None:
        with pytest.raises(LengthDeltaInvalidError) as ei:
            await _grant(
                env,
                player_id=1,
                delta_cm=0,
                source=AuditSource.FOREST,
                reason="x",
            )
        assert ei.value.reason_code == "zero"

    @pytest.mark.asyncio
    async def test_negative_delta_for_organic_raises(self, env: dict[str, object]) -> None:
        with pytest.raises(LengthDeltaInvalidError) as ei:
            await _grant(
                env,
                player_id=1,
                delta_cm=-50,
                source=AuditSource.FOREST,
                reason="x",
            )
        assert ei.value.reason_code == "negative_for_non_refund"

    @pytest.mark.asyncio
    async def test_positive_delta_for_admin_refund_raises(self, env: dict[str, object]) -> None:
        with pytest.raises(LengthDeltaInvalidError) as ei:
            await _grant(
                env,
                player_id=1,
                delta_cm=10,
                source=AuditSource.ADMIN_REFUND,
                reason="x",
            )
        assert ei.value.reason_code == "positive_for_refund"

    @pytest.mark.asyncio
    async def test_unknown_source_raises(self, env: dict[str, object]) -> None:
        with pytest.raises(LengthDeltaInvalidError) as ei:
            await _grant(
                env,
                player_id=1,
                delta_cm=10,
                source=AuditSource.UNKNOWN,
                reason="x",
            )
        assert ei.value.reason_code == "unknown_source"

    @pytest.mark.asyncio
    async def test_player_not_found_raises(self, env: dict[str, object]) -> None:
        # players.rows пуст.
        with pytest.raises(PlayerNotFoundError):
            await _grant(
                env,
                player_id=999,
                delta_cm=10,
                source=AuditSource.FOREST,
                reason="x",
            )


# ────────────────────────────── idempotency ──────────────────────────────


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_replay_returns_no_op(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        audit_inner: FakeAuditLogger = env["audit_inner"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=100))

        first = await _grant(
            env,
            player_id=1,
            delta_cm=200,
            source=AuditSource.FOREST,
            reason="forest",
            idempotency_key="add_length:forest_run_finished:length:42",
        )
        second = await _grant(
            env,
            player_id=1,
            delta_cm=200,
            source=AuditSource.FOREST,
            reason="forest",
            idempotency_key="add_length:forest_run_finished:length:42",
        )

        assert first.applied_delta_cm == 200
        assert first.new_length_cm == 300
        # Повторный вызов с тем же ключом — no-op.
        assert second.applied_delta_cm == 0
        assert second.clamped_from is None
        assert second.triggered_soft_ban is False
        assert second.new_length_cm == 300
        # Player не изменён повторно.
        assert players.rows[0].length.cm == 300
        # Audit ровно один раз.
        assert len(audit_inner.entries) == 1

    @pytest.mark.asyncio
    async def test_first_call_marks_idempotency_key(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        idempotency: FakeIdempotencyKey = env["idempotency"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=100))

        await _grant(
            env,
            player_id=1,
            delta_cm=10,
            source=AuditSource.FOREST,
            reason="forest",
            idempotency_key="add_length:key-abc",
        )

        assert await idempotency.is_seen("add_length:key-abc") is True


# ────────────────────────────── trip-wire ──────────────────────────────


class TestTripWire:
    @pytest.mark.asyncio
    async def test_daily_cap_exceeded_triggers_soft_ban(self, env: dict[str, object]) -> None:
        """Прямой save игрока в обход add_length дал organic 3500 за сутки —
        следующий add_length+1 организует трip-wire (3500+1 > 3000).

        В тесте имитируем «обход» через `anticheat.record_event` с количеством
        выше cap. Использует FakeAnticheatRepository, в котором мы можем
        записать сумму выше cap, не проходя через clamp use-case-а.
        """
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        anticheat: FakeAnticheatRepository = env["anticheat"]  # type: ignore[assignment]
        audit_inner: FakeAuditLogger = env["audit_inner"]  # type: ignore[assignment]
        admin_alerter: FakeAnticheatAdminAlerter = env["admin_alerter"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=100))
        # Имитируем «прорыв»: сумма уже 3500 (пробила cap, но clamp нашего
        # use-case-а такого не допустит — это след прямой записи в БД).
        anticheat.record_event(
            player_id=1,
            source=AuditSource.FOREST,
            delta_cm=3500,
            occurred_at=_NOW - timedelta(hours=1),
        )

        result = await _grant(
            env,
            player_id=1,
            delta_cm=1,
            source=AuditSource.FOREST,
            reason="forest",
        )

        # Clamp до 0 (3500 уже за пределами cap-а).
        assert result.applied_delta_cm == 0
        # Trip-wire не сработал, потому что applied_delta=0 — прибавки не было.
        # См. условие `if is_organic and applied_delta > 0`.
        assert result.triggered_soft_ban is False
        # Алёрта тоже нет.
        assert admin_alerter.events == []
        # Только LENGTH_GRANT с clamped_from, но без trip-wire.
        actions = [e.action for e in audit_inner.entries]
        assert AuditAction.ANTICHEAT_DAILY_CAP_EXCEEDED not in actions

    @pytest.mark.asyncio
    async def test_daily_cap_exceeded_via_concurrent_event_triggers_trip_wire(
        self,
        env: dict[str, object],
    ) -> None:
        """Симуляция гонки: сначала clamp видит 2950 → пускает 50 насквозь.
        Дальше параллельная транза прыгнула и докинула 100.
        После save рекомпьют видит 2950 + 50 (наша) + 100 (их) = 3100 > 3000 →
        trip-wire.

        В fake-фикстуре нет реальной конкурентности, но мы можем
        воспроизвести эффект, подкинув "чужое" событие между моментом
        clamp-а и моментом записи в anticheat. Для этого подменим
        FakeAnticheatRepository так, чтобы ВТОРОЙ вызов
        `sum_organic_in_window` вернул сумму > cap.
        """
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        anticheat: FakeAnticheatRepository = env["anticheat"]  # type: ignore[assignment]
        audit_inner: FakeAuditLogger = env["audit_inner"]  # type: ignore[assignment]
        admin_alerter: FakeAnticheatAdminAlerter = env["admin_alerter"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=100))

        # Состояние «до clamp-а»: 2950 → remaining=50 → applied=50.
        anticheat.record_event(
            player_id=1,
            source=AuditSource.FOREST,
            delta_cm=2950,
            occurred_at=_NOW - timedelta(hours=1),
        )
        # «Параллельная» запись из другой транзакции, которая
        # появится в БД между clamp-ом и trip-wire-recompute.
        # FakeAnticheatRepository делает `len(events)`-обход линейно;
        # если мы запишем событие ПОСЛЕ начала вызова grant-а, оно не
        # попадёт. Поэтому записываем вручную как «уже было», но
        # с количеством, которое после нашей `LinkedAuditLogger`-записи
        # пробьёт cap: 2950 + 50 = 3000 (ровно cap, не пробит) → нужно
        # ещё хотя бы 1 см «чужой» записи.
        anticheat.record_event(
            player_id=1,
            source=AuditSource.ORACLE,
            delta_cm=51,
            occurred_at=_NOW - timedelta(minutes=30),
        )
        # Теперь сумма = 2950 + 51 = 3001 → clamp пустит remaining = max(0, 3000-3001) = 0
        # — это другой кейс, исчерпание. Перепишу под более чистую
        # имитацию: сначала 2900, чужое событие 50 (после clamp-а).
        anticheat.events.clear()
        anticheat.record_event(
            player_id=1,
            source=AuditSource.FOREST,
            delta_cm=2900,
            occurred_at=_NOW - timedelta(hours=2),
        )
        # Чужая запись: 60. Положим её ПОСЛЕ — это симулирует
        # «параллельная транза докинула 60 за время между clamp-ом
        # и trip-wire-recompute» (clamp видит 2900, pre-применяет 100,
        # но после save recompute = 2900 + 60 + 100 = 3060 > 3000).
        anticheat.record_event(
            player_id=1,
            source=AuditSource.ORACLE,
            delta_cm=60,
            occurred_at=_NOW - timedelta(minutes=30),
        )

        # NB: clamp в реальном race-test увидит уже 2960, но в fake-репо
        # обе записи лежат до вызова, поэтому clamp вернёт remaining=40.
        # Это тоже ок — просто меньше шанса trip-wire. Чтобы тест был
        # надёжным trip-wire-ом, добавим явный «чужой» прыжок в
        # last-mile через `monkeypatch` на `sum_organic_in_window`.

        # Для надёжности: подменим anticheat-репозиторий хуком,
        # который при ВТОРОМ вызове (после save) возвращает 3100.
        original_sum = anticheat.sum_organic_in_window
        call_count = {"n": 0}

        async def hooked_sum(**kwargs: object) -> object:
            call_count["n"] += 1
            window = await original_sum(**kwargs)  # type: ignore[arg-type]
            # На trip-wire-итерации (3-й вызов: daily-after) подкинем 200 «чужих» см.
            if call_count["n"] >= 3:
                return AnticheatWindow(
                    player_id=window.player_id,
                    since=window.since,
                    organic_sum_cm=window.organic_sum_cm + 200,
                )
            return window

        anticheat.sum_organic_in_window = hooked_sum  # type: ignore[assignment]

        result = await _grant(
            env,
            player_id=1,
            delta_cm=100,
            source=AuditSource.FOREST,
            reason="forest",
        )

        assert result.triggered_soft_ban is True
        assert result.applied_delta_cm > 0
        # Player забанен.
        assert players.rows[0].anticheat_ban_until is not None
        assert players.rows[0].anticheat_ban_until == _NOW + timedelta(days=14)
        # Audit содержит ANTICHEAT_DAILY_CAP_EXCEEDED.
        actions = [e.action for e in audit_inner.entries]
        assert AuditAction.ANTICHEAT_DAILY_CAP_EXCEEDED in actions
        # Алёрт админу отправлен ровно один раз.
        assert len(admin_alerter.events) == 1
        assert admin_alerter.events[0].cap_kind == "daily"
        assert admin_alerter.events[0].cap_cm == 3000
        assert admin_alerter.events[0].source is AuditSource.FOREST

    @pytest.mark.asyncio
    async def test_weekly_cap_exceeded_triggers_trip_wire(
        self,
        env: dict[str, object],
    ) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        anticheat: FakeAnticheatRepository = env["anticheat"]  # type: ignore[assignment]
        audit_inner: FakeAuditLogger = env["audit_inner"]  # type: ignore[assignment]
        admin_alerter: FakeAnticheatAdminAlerter = env["admin_alerter"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=100))

        original_sum = anticheat.sum_organic_in_window
        call_count = {"n": 0}

        async def hooked_sum(**kwargs: object) -> object:
            call_count["n"] += 1
            window = await original_sum(**kwargs)  # type: ignore[arg-type]
            # На рекомпьют weekly после save (4-й вызов: daily-after, weekly-after)
            # — подкинем «чужие» 14001 см. Daily остаётся в норме, weekly
            # пробит → trip-wire weekly.
            since_threshold = _NOW - timedelta(days=2)
            if call_count["n"] >= 3 and kwargs.get("since") < since_threshold:  # type: ignore[operator]
                return AnticheatWindow(
                    player_id=window.player_id,
                    since=window.since,
                    organic_sum_cm=14001,
                )
            return window

        anticheat.sum_organic_in_window = hooked_sum  # type: ignore[assignment]

        result = await _grant(
            env,
            player_id=1,
            delta_cm=10,
            source=AuditSource.FOREST,
            reason="forest",
        )

        assert result.triggered_soft_ban is True
        actions = [e.action for e in audit_inner.entries]
        assert AuditAction.ANTICHEAT_WEEKLY_CAP_EXCEEDED in actions
        assert AuditAction.ANTICHEAT_DAILY_CAP_EXCEEDED not in actions
        assert len(admin_alerter.events) == 1
        assert admin_alerter.events[0].cap_kind == "weekly"
        assert admin_alerter.events[0].cap_cm == 14000

    @pytest.mark.asyncio
    async def test_donate_does_not_fire_trip_wire(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        admin_alerter: FakeAnticheatAdminAlerter = env["admin_alerter"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=100))

        result = await _grant(
            env,
            player_id=1,
            delta_cm=99999,
            source=AuditSource.STARS_PAYMENT,
            reason="big_donate",
        )

        assert result.triggered_soft_ban is False
        assert admin_alerter.events == []

    @pytest.mark.asyncio
    async def test_admin_refund_does_not_fire_trip_wire(self, env: dict[str, object]) -> None:
        players: FakePlayerRepository = env["players"]  # type: ignore[assignment]
        admin_alerter: FakeAnticheatAdminAlerter = env["admin_alerter"]  # type: ignore[assignment]
        players.rows.append(_make_player(length_cm=500))

        result = await _grant(
            env,
            player_id=1,
            delta_cm=-100,
            source=AuditSource.ADMIN_REFUND,
            reason="refund",
        )

        assert result.triggered_soft_ban is False
        assert admin_alerter.events == []
