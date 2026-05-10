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
from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.clan import Clan, ClanMember, ClanStatus
from pipirik_wars.domain.clan.entities import ClanMemberRole
from pipirik_wars.domain.clan.value_objects import ChatKind, ClanTitle
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
    FakeClanRepository,
    FakeClock,
    FakeIdempotencyKey,
    FakeOracleHistoryRepository,
    FakeOracleTemplateProvider,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance, valid_balance_payload


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
    clans: FakeClanRepository | None = None,
) -> tuple[
    InvokeOracle,
    FakePlayerRepository,
    FakeOracleHistoryRepository,
    FakeOracleTemplateProvider,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
    FakeClanRepository,
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
    used_clans = clans or FakeClanRepository()
    use_case = InvokeOracle(
        uow=uow,
        players=players,
        history=history,
        templates=templates,
        balance=balance,
        random=FakeRandom(seed=seed),
        length_granter=length_granter,
        clock=used_clock,
        clans=used_clans,
    )
    return use_case, players, history, templates, audit, uow, used_clock, used_clans


@pytest.mark.asyncio
class TestInvokeOracleHappyPath:
    async def test_grants_length_and_records_invocation(self) -> None:
        use_case, players, history, _, audit, uow, _, _ = _build_use_case()
        seeded = _seed_player(players, tg_id=100, length_cm=30)

        out = await use_case.execute(InvokeOracleInput(tg_id=100))

        # Базовый бросок (`result.bonus_cm`) — строго в [1..20] см.
        assert 1 <= out.result.bonus_cm <= 20
        # Без племени (FakeClanRepository пуст) — бонус-за-племена = 0.
        assert out.base_cm == out.result.bonus_cm
        assert out.tribe_bonus_cm == 0
        assert out.n_active_tribes == 0
        assert out.total_cm == out.result.bonus_cm
        # Длина выросла ровно на bonus_cm.
        assert out.player_after.length.cm == seeded.length.cm + out.result.bonus_cm
        # Появилась ровно одна запись в истории; `bonus_cm` = итог
        # (база + племена = база, т.к. племен нет).
        assert len(history.rows) == 1
        rec = history.rows[0]
        assert rec.player_id == seeded.id
        assert rec.bonus_cm == out.total_cm
        assert rec.template_id == out.result.template.id
        # Audit-запись `LENGTH_GRANT` (базовая) оформлена через AddLength
        # (Спринт 1.6.F): `source=ORACLE`, `delta_cm=base_cm`, suffix `:base`,
        # `reason="oracle_base"`. Без племен — второй проводки нет.
        assert len(audit.entries) == 1
        ae = audit.entries[0]
        assert ae.action is AuditAction.LENGTH_GRANT
        assert ae.source is AuditSource.ORACLE
        assert ae.delta_cm == out.result.bonus_cm
        assert ae.actor_id == seeded.tg_id
        assert ae.target_kind == "player"
        assert ae.target_id == str(seeded.id)
        assert ae.reason == "oracle_base"
        assert ae.idempotency_key is not None
        assert ae.idempotency_key.startswith("add_length:oracle:")
        assert ae.idempotency_key.endswith(":base")
        # Транзакция закрылась.
        assert uow.commits == 1
        assert uow.rollbacks == 0

    async def test_player_not_found_raises_and_no_writes(self) -> None:
        use_case, players, history, _, audit, uow, _, _ = _build_use_case()

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
        use_case, players, history, _, audit, uow, clock, _ = _build_use_case()
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
        use_case, players, history, _, _audit, _uow, clock, _ = _build_use_case()
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
        use_case, players, history, _, _, _, _, _ = _build_use_case()
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
        use_case, players, history, _, _, _, _, _ = _build_use_case(clock=clock)
        _seed_player(players, tg_id=100, length_cm=30)

        await use_case.execute(InvokeOracleInput(tg_id=100))

        # Запись должна стоять на 5 мая (Москва), не на 4 мая (UTC).
        assert history.rows[0].moscow_date == date(2026, 5, 5)


def _seed_active_clan(
    clans: FakeClanRepository,
    *,
    clan_id: int,
    chat_id: int,
    member_player_ids: list[int],
) -> None:
    """Сид-хелпер для tribe-bonus-тестов: один ACTIVE-клан с заданным
    списком участников-игроков. Регистрирует клан в `clans.rows`
    и вкладывает всех игроков в `clans.members` (это совпадает с
    контрактом FakeClanRepository.count_active_for_player, который берёт
    подсчёт именно из `members`).
    """
    clans.rows.append(
        Clan(
            id=clan_id,
            chat_id=chat_id,
            chat_kind=ChatKind.SUPERGROUP,
            title=ClanTitle(value=f"Clan-{clan_id}"),
            status=ClanStatus.ACTIVE,
            created_at=datetime(2026, 5, 1, tzinfo=UTC),
            updated_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
    )
    for pid in member_player_ids:
        clans.members.append(
            ClanMember(
                clan_id=clan_id,
                player_id=pid,
                role=ClanMemberRole.MEMBER,
                joined_at=datetime(2026, 5, 1, tzinfo=UTC),
            )
        )


@pytest.mark.asyncio
class TestInvokeOracleTribeBonus:
    """Спринт 3.6-A (ГДД §11.1): бонус-за-племена в `/oracle`.

    Покрывает:
    - «игрок без племени» → бонус 0, второй `LENGTH_GRANT` не пишется;
    - «игрок в активном племени» (×1) → +`cm_per_tribe` см вторым grant-ом;
    - кап клампит бонус (`n_active * cm_per_tribe > cap_cm` → `cap_cm`);
    - «племя меньше min_tribe_size» или frozen — не засчитывается;
    - `enabled=false` в конфиге → `clans` вообще не зовётся;
    - идемпотент-ключи `:base` и `:tribe_bonus` разные (не перебиваются).
    """

    async def test_no_tribe_membership_means_no_bonus_and_no_second_grant(self) -> None:
        """FakeClanRepository пуст → `n_active=0` → бонус 0 → второго grant-а нет."""
        use_case, players, _, _, audit, _, _, clans = _build_use_case()
        _seed_player(players, tg_id=100, length_cm=30)
        # Клан-список пуст — игрок не в племени.
        assert clans.rows == []

        out = await use_case.execute(InvokeOracleInput(tg_id=100))

        assert out.tribe_bonus_cm == 0
        assert out.n_active_tribes == 0
        # Ровно одна audit-запись (база), второй (`oracle_tribe_bonus`) нет.
        assert len(audit.entries) == 1
        assert audit.entries[0].source is AuditSource.ORACLE
        assert audit.entries[0].reason == "oracle_base"

    async def test_single_active_tribe_grants_cm_per_tribe(self) -> None:
        """5 участников включая игрока (>= min_tribe_size=4) → +1 см бонуса."""
        use_case, players, history, _, audit, _, _, clans = _build_use_case()
        seeded = _seed_player(players, tg_id=100, length_cm=30)
        assert seeded.id is not None
        _seed_active_clan(
            clans,
            clan_id=1,
            chat_id=-100,
            member_player_ids=[seeded.id, 2, 3, 4, 5],
        )

        out = await use_case.execute(InvokeOracleInput(tg_id=100))

        # cm_per_tribe=1, n=1 → +1 см.
        assert out.n_active_tribes == 1
        assert out.tribe_bonus_cm == 1
        assert out.total_cm == out.base_cm + 1
        # `oracle_invocations.bonus_cm` — итог.
        assert history.rows[0].bonus_cm == out.total_cm
        # Две audit-записи: база + бонус-за-племена.
        assert len(audit.entries) == 2
        base_ae = audit.entries[0]
        tribe_ae = audit.entries[1]
        assert base_ae.source is AuditSource.ORACLE
        assert base_ae.delta_cm == out.base_cm
        assert base_ae.reason == "oracle_base"
        assert base_ae.idempotency_key is not None
        assert base_ae.idempotency_key.endswith(":base")
        assert tribe_ae.source is AuditSource.ORACLE_TRIBE_BONUS
        assert tribe_ae.delta_cm == 1
        assert tribe_ae.reason == "oracle_tribe_bonus"
        assert tribe_ae.idempotency_key is not None
        assert tribe_ae.idempotency_key.endswith(":tribe_bonus")
        # Ключи разные — иначе вторая проводка была бы no-op-ом.
        assert base_ae.idempotency_key != tribe_ae.idempotency_key
        # Длина выросла на итог (база + бонус).
        assert out.player_after.length.cm == seeded.length.cm + out.total_cm

    async def test_tribe_smaller_than_min_size_not_counted(self) -> None:
        """Племя из 3 игроков (< min_tribe_size=4) → не засчитывается."""
        use_case, players, _, _, audit, _, _, clans = _build_use_case()
        seeded = _seed_player(players, tg_id=100, length_cm=30)
        assert seeded.id is not None
        _seed_active_clan(
            clans,
            clan_id=1,
            chat_id=-100,
            member_player_ids=[seeded.id, 2, 3],  # всего 3 участника.
        )

        out = await use_case.execute(InvokeOracleInput(tg_id=100))

        assert out.n_active_tribes == 0
        assert out.tribe_bonus_cm == 0
        assert len(audit.entries) == 1

    async def test_frozen_tribe_not_counted(self) -> None:
        """FROZEN-клан (4 участника) → не засчитывается, бонус 0."""
        use_case, players, _, _, audit, _, _, clans = _build_use_case()
        seeded = _seed_player(players, tg_id=100, length_cm=30)
        assert seeded.id is not None
        clans.rows.append(
            Clan(
                id=1,
                chat_id=-100,
                chat_kind=ChatKind.SUPERGROUP,
                title=ClanTitle(value="Frozen Clan"),
                status=ClanStatus.FROZEN,
                created_at=datetime(2026, 5, 1, tzinfo=UTC),
                updated_at=datetime(2026, 5, 1, tzinfo=UTC),
            )
        )
        for pid in (seeded.id, 2, 3, 4):
            clans.members.append(
                ClanMember(
                    clan_id=1,
                    player_id=pid,
                    role=ClanMemberRole.MEMBER,
                    joined_at=datetime(2026, 5, 1, tzinfo=UTC),
                )
            )

        out = await use_case.execute(InvokeOracleInput(tg_id=100))

        assert out.n_active_tribes == 0
        assert out.tribe_bonus_cm == 0
        assert len(audit.entries) == 1

    async def test_cap_clamps_when_count_times_per_tribe_exceeds_cap(self) -> None:
        """Баланс-конфиг с cm_per_tribe=200, cap_cm=131, одно племя → бонус
        клампится на cap (200 -> 131).

        Эмулирует «200 активных племён при cm_per_tribe=1, cap_cm=131» через
        эквивалентный «1 активное племя при cm_per_tribe=200, cap_cm=131» —
        формула идентична (`min(n*cm, cap)`), но не требует 200 fake-кланов.
        """
        payload = valid_balance_payload()
        payload["oracle"]["tribe_bonus"] = {
            "enabled": True,
            "cm_per_tribe": 200,
            "cap_cm": 131,
            "min_tribe_size": 4,
        }
        cfg = BalanceConfig.model_validate(payload)

        # Пересобираем use-case с этим конфигом.
        uow = FakeUnitOfWork()
        players = FakePlayerRepository()
        history = FakeOracleHistoryRepository()
        templates = FakeOracleTemplateProvider(
            catalog={
                "ru": (OracleTemplate(id="oracle.ru.0001", text="T"),),
            },
        )
        audit = FakeAuditLogger()
        clock = FakeClock(datetime(2026, 5, 5, 9, 0, tzinfo=UTC))
        balance = FakeBalanceConfig(cfg)
        length_granter = AddLength(
            uow=uow,
            players=players,
            anticheat=FakeAnticheatRepository(),
            audit=audit,
            balance=balance,
            clock=clock,
            idempotency=FakeIdempotencyKey(),
            admin_alerter=FakeAnticheatAdminAlerter(),
        )
        clans = FakeClanRepository()
        use_case = InvokeOracle(
            uow=uow,
            players=players,
            history=history,
            templates=templates,
            balance=balance,
            random=FakeRandom(seed=1),
            length_granter=length_granter,
            clock=clock,
            clans=clans,
        )
        seeded = _seed_player(players, tg_id=100, length_cm=30)
        assert seeded.id is not None
        _seed_active_clan(
            clans,
            clan_id=1,
            chat_id=-100,
            member_player_ids=[seeded.id, 2, 3, 4],  # 4 >= min_tribe_size=4.
        )

        out = await use_case.execute(InvokeOracleInput(tg_id=100))

        assert out.n_active_tribes == 1
        # 1 * 200 = 200 см, клампится до cap_cm=131.
        assert out.tribe_bonus_cm == 131
        # Audit: база + cap-бонус.
        assert len(audit.entries) == 2
        assert audit.entries[1].delta_cm == 131
        assert audit.entries[1].source is AuditSource.ORACLE_TRIBE_BONUS

    async def test_disabled_flag_skips_clan_repo_query(self) -> None:
        """При `tribe_bonus.enabled=false` репозиторий кланов вообще не зовётся."""
        payload = valid_balance_payload()
        payload["oracle"]["tribe_bonus"] = {
            "enabled": False,
            "cm_per_tribe": 1,
            "cap_cm": 131,
            "min_tribe_size": 4,
        }
        cfg = BalanceConfig.model_validate(payload)

        uow = FakeUnitOfWork()
        players = FakePlayerRepository()
        history = FakeOracleHistoryRepository()
        templates = FakeOracleTemplateProvider(
            catalog={
                "ru": (OracleTemplate(id="oracle.ru.0001", text="T"),),
            },
        )
        audit = FakeAuditLogger()
        clock = FakeClock(datetime(2026, 5, 5, 9, 0, tzinfo=UTC))
        balance = FakeBalanceConfig(cfg)
        length_granter = AddLength(
            uow=uow,
            players=players,
            anticheat=FakeAnticheatRepository(),
            audit=audit,
            balance=balance,
            clock=clock,
            idempotency=FakeIdempotencyKey(),
            admin_alerter=FakeAnticheatAdminAlerter(),
        )

        # Спец-фейк, падающий на любом вызове count_active_for_player —
        # если use-case вызовет клановый репо при disabled=false, тест упадёт.
        class _RaisingClanRepo(FakeClanRepository):
            async def count_active_for_player(self, *, player_id: int, min_tribe_size: int) -> int:
                raise AssertionError(
                    "clans.count_active_for_player must NOT be called when "
                    "oracle.tribe_bonus.enabled is False"
                )

        clans = _RaisingClanRepo()
        use_case = InvokeOracle(
            uow=uow,
            players=players,
            history=history,
            templates=templates,
            balance=balance,
            random=FakeRandom(seed=1),
            length_granter=length_granter,
            clock=clock,
            clans=clans,
        )
        _seed_player(players, tg_id=100, length_cm=30)

        out = await use_case.execute(InvokeOracleInput(tg_id=100))

        assert out.n_active_tribes == 0
        assert out.tribe_bonus_cm == 0
        assert len(audit.entries) == 1  # только базовый grant.
