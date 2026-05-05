"""Unit-тесты `InvokeOracle` (Спринт 1.4.B; миграция на ILengthGranter — 1.6.F).

Покрывают acceptance ПД 1.4.4:
- повторный `/oracle` в тот же московский день — отказ;
- следующий день — успех;
- успешный вызов прибавляет длину и пишет audit `LENGTH_GRANT` (через
  `ILengthGranter` / `AddLength`, а не напрямую — Спринт 1.6.F);
- запись `oracle_invocations` сохраняется с правильным
  `(player_id, moscow_date, template_id)`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from pipirik_wars.application.dto.inputs import InvokeOracleInput
from pipirik_wars.application.oracle import InvokeOracle
from pipirik_wars.application.progression import AddLength
from pipirik_wars.domain.oracle import OracleAlreadyUsedTodayError, OracleTemplate
from pipirik_wars.domain.player import (
    Player,
    PlayerNotFoundError,
    PlayerStatus,
    Thickness,
)
from pipirik_wars.domain.player.value_objects import Length, Username
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.domain.shared.ports.audit import AuditSource
from tests.fakes import (
    FakeAnticheatAdminAlerter,
    FakeAnticheatRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakeIdempotencyKey,
    FakeOracleHistoryRepository,
    FakeOracleTemplateProvider,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance


def _seed_player(repo: FakePlayerRepository, *, tg_id: int = 100, length_cm: int = 30) -> Player:
    player = Player(
        id=1,
        tg_id=tg_id,
        username=Username(value="alice"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=datetime(2026, 5, 4, tzinfo=UTC),
        updated_at=datetime(2026, 5, 4, tzinfo=UTC),
    )
    repo.rows.append(player)
    return player


def _build_use_case(
    *,
    clock: FakeClock | None = None,
    seed: int = 1,
) -> tuple[
    InvokeOracle,
    FakePlayerRepository,
    FakeOracleHistoryRepository,
    FakeOracleTemplateProvider,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    history = FakeOracleHistoryRepository()
    templates = FakeOracleTemplateProvider(
        catalog={
            "ru": (
                OracleTemplate(id="oracle.ru.0001", text="Текст 1, {user}!"),
                OracleTemplate(id="oracle.ru.0002", text="Текст 2"),
                OracleTemplate(id="oracle.ru.0003", text="Текст 3"),
            ),
        },
    )
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(datetime(2026, 5, 5, 9, 0, tzinfo=UTC))  # 12:00 МСК
    balance = FakeBalanceConfig(build_valid_balance())
    # Прибавка длины — через ILengthGranter (Спринт 1.6.F). Все anti-cheat-
    # зависимости мокаются фейками; cap (3000/14000) большой → клампа нет.
    length_granter = AddLength(
        uow=uow,
        players=players,
        anticheat=FakeAnticheatRepository(),
        audit=audit,
        balance=balance,
        clock=used_clock,
        idempotency=FakeIdempotencyKey(),
        admin_alerter=FakeAnticheatAdminAlerter(),
    )
    use_case = InvokeOracle(
        uow=uow,
        players=players,
        history=history,
        templates=templates,
        balance=balance,
        random=FakeRandom(seed=seed),
        length_granter=length_granter,
        clock=used_clock,
    )
    return use_case, players, history, templates, audit, uow, used_clock


@pytest.mark.asyncio
class TestInvokeOracleHappyPath:
    async def test_grants_length_and_records_invocation(self) -> None:
        use_case, players, history, _, audit, uow, _ = _build_use_case()
        seeded = _seed_player(players, tg_id=100, length_cm=30)

        out = await use_case.execute(InvokeOracleInput(tg_id=100))

        # Прибавка длины строго в [1..20] см.
        assert 1 <= out.result.bonus_cm <= 20
        # Длина выросла ровно на bonus_cm.
        assert out.player_after.length.cm == seeded.length.cm + out.result.bonus_cm
        # Появилась ровно одна запись в истории.
        assert len(history.rows) == 1
        rec = history.rows[0]
        assert rec.player_id == seeded.id
        assert rec.bonus_cm == out.result.bonus_cm
        assert rec.template_id == out.result.template.id
        # Audit-запись `LENGTH_GRANT` оформлена через AddLength (Спринт 1.6.F):
        # `source=ORACLE`, `delta_cm=bonus`, `idempotency_key=add_length:oracle:...`.
        assert len(audit.entries) == 1
        ae = audit.entries[0]
        assert ae.action is AuditAction.LENGTH_GRANT
        assert ae.source is AuditSource.ORACLE
        assert ae.delta_cm == out.result.bonus_cm
        assert ae.actor_id == seeded.tg_id
        assert ae.target_kind == "player"
        assert ae.target_id == str(seeded.id)
        assert ae.reason == "oracle_invocation"
        assert ae.idempotency_key is not None
        assert ae.idempotency_key.startswith("add_length:oracle:")
        # Транзакция закрылась.
        assert uow.commits == 1
        assert uow.rollbacks == 0

    async def test_player_not_found_raises_and_no_writes(self) -> None:
        use_case, players, history, _, audit, uow, _ = _build_use_case()

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(InvokeOracleInput(tg_id=404))

        assert players.rows == []
        assert history.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1


@pytest.mark.asyncio
class TestInvokeOracleCooldown:
    """Acceptance ПД 1.4.4: повтор в тот же день — отказ; на следующий — успех."""

    async def test_second_invocation_same_moscow_day_rejected(self) -> None:
        use_case, players, history, _, audit, uow, clock = _build_use_case()
        _seed_player(players, tg_id=100, length_cm=30)

        # Первый /oracle — успешен.
        await use_case.execute(InvokeOracleInput(tg_id=100))
        assert len(history.rows) == 1

        # Тот же московский день, второй вызов: спустя 5 часов всё ещё 5 мая по Москве.
        clock.advance(hours=5)
        with pytest.raises(OracleAlreadyUsedTodayError) as exc_info:
            await use_case.execute(InvokeOracleInput(tg_id=100))

        # Записей в истории/audit-е больше не появилось.
        assert len(history.rows) == 1
        assert len(audit.entries) == 1
        assert exc_info.value.player_id == 1
        assert exc_info.value.moscow_date == clock.moscow_date()

    async def test_next_moscow_day_invocation_succeeds(self) -> None:
        use_case, players, history, _, _audit, _uow, clock = _build_use_case()
        _seed_player(players, tg_id=100, length_cm=30)

        await use_case.execute(InvokeOracleInput(tg_id=100))
        first_date = clock.moscow_date()

        # Прокрутили 24 часа — это уже следующий день по Москве.
        clock.advance(days=1)
        assert clock.moscow_date() != first_date

        await use_case.execute(InvokeOracleInput(tg_id=100))
        assert len(history.rows) == 2
        assert {r.moscow_date for r in history.rows} == {first_date, clock.moscow_date()}

    async def test_two_players_same_day_independent(self) -> None:
        """Лимит — на (player_id, moscow_date), не глобальный."""
        use_case, players, history, _, _, _, _ = _build_use_case()
        _seed_player(players, tg_id=100, length_cm=30)
        # Второй игрок.
        players.rows.append(
            Player(
                id=2,
                tg_id=200,
                username=Username(value="bob"),
                length=Length(cm=10),
                thickness=Thickness(level=1),
                title=None,
                name=None,
                status=PlayerStatus.ACTIVE,
                created_at=datetime(2026, 5, 4, tzinfo=UTC),
                updated_at=datetime(2026, 5, 4, tzinfo=UTC),
            )
        )

        await use_case.execute(InvokeOracleInput(tg_id=100))
        await use_case.execute(InvokeOracleInput(tg_id=200))

        assert len(history.rows) == 2


@pytest.mark.asyncio
class TestInvokeOracleMoscowTzEdge:
    """Граница TZ: 23:30 UTC = 02:30 МСК (следующий день)."""

    async def test_uses_moscow_calendar_date_not_utc(self) -> None:
        # 4 мая 23:30 UTC = 5 мая 02:30 МСК.
        clock = FakeClock(datetime(2026, 5, 4, 23, 30, tzinfo=UTC))
        use_case, players, history, _, _, _, _ = _build_use_case(clock=clock)
        _seed_player(players, tg_id=100, length_cm=30)

        await use_case.execute(InvokeOracleInput(tg_id=100))

        # Запись должна стоять на 5 мая (Москва), не на 4 мая (UTC).
        assert history.rows[0].moscow_date == date(2026, 5, 5)
