"""Unit-тесты `SetPlayerLocale` (Спринт 1.5.F, ПД 1.5.2).

Покрываем:
1. Игрок есть → locale_override записан, audit-запись `PLAYER_LOCALE_SET`.
2. Игрока нет → `PlayerNotFoundError`, нет save / нет audit.
3. Идемпотентность: повторный вызов с той же локалью — entity не
   переписывается (`updated_at` тот же), но audit-запись пишется
   (это полезно для метрик «как часто пользователь жмёт кнопку»).
4. Сброс override-а через `locale=None` → колонка `None`.
5. Невалидная локаль (например, `Locale("fr")`) → `ValueError` (защита
   от обхода SUPPORTED_LOCALES снаружи; handler уже фильтрует, но
   use-case — последняя линия обороны).
6. UoW: при не-найденном игроке транзакция роллбэкается, save не
   вызывался.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.i18n import Locale
from pipirik_wars.application.player import SetPlayerLocale
from pipirik_wars.domain.player import (
    Player,
    PlayerName,
    PlayerNotFoundError,
    PlayerStatus,
    Thickness,
    Title,
)
from pipirik_wars.domain.player.value_objects import Length, Username
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeAuditLogger,
    FakeClock,
    FakePlayerRepository,
    FakeUnitOfWork,
)


def _seed_player(
    repo: FakePlayerRepository,
    *,
    tg_id: int = 100,
    locale_override: str | None = None,
) -> Player:
    player = Player(
        id=1,
        tg_id=tg_id,
        username=Username(value="alice"),
        length=Length(cm=20),
        thickness=Thickness(level=1),
        title=Title.NEWBIE,
        name=PlayerName(value="Колян"),
        status=PlayerStatus.ACTIVE,
        created_at=datetime(2026, 5, 4, tzinfo=UTC),
        updated_at=datetime(2026, 5, 4, tzinfo=UTC),
        locale_override=locale_override,
    )
    repo.rows.append(player)
    return player


def _build_use_case() -> tuple[
    SetPlayerLocale,
    FakePlayerRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    audit = FakeAuditLogger()
    clock = FakeClock(datetime(2026, 5, 5, 12, 0, tzinfo=UTC))
    use_case = SetPlayerLocale(uow=uow, players=players, audit=audit, clock=clock)
    return use_case, players, audit, uow, clock


@pytest.mark.asyncio
class TestSetPlayerLocale:
    async def test_sets_override_for_registered_player(self) -> None:
        use_case, players, audit, uow, _ = _build_use_case()
        _seed_player(players, tg_id=42, locale_override=None)

        result = await use_case.execute(tg_id=42, locale=Locale(code="ru"))

        assert result.locale_override == "ru"
        assert result.previous_locale_override is None
        assert players.rows[0].locale_override == "ru"
        assert uow.commits == 1
        assert uow.rollbacks == 0
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.PLAYER_LOCALE_SET
        assert entry.before == {"locale_override": None}
        assert entry.after == {"locale_override": "ru"}
        assert entry.target_kind == "player"

    async def test_switches_from_one_locale_to_another(self) -> None:
        use_case, players, audit, _, _ = _build_use_case()
        _seed_player(players, tg_id=42, locale_override="ru")

        result = await use_case.execute(tg_id=42, locale=Locale(code="en"))

        assert result.previous_locale_override == "ru"
        assert result.locale_override == "en"
        assert players.rows[0].locale_override == "en"
        assert audit.entries[0].before == {"locale_override": "ru"}
        assert audit.entries[0].after == {"locale_override": "en"}

    async def test_resets_override_with_none(self) -> None:
        use_case, players, audit, _, _ = _build_use_case()
        _seed_player(players, tg_id=42, locale_override="ru")

        result = await use_case.execute(tg_id=42, locale=None)

        assert result.locale_override is None
        assert result.previous_locale_override == "ru"
        assert players.rows[0].locale_override is None
        assert audit.entries[0].after == {"locale_override": None}

    async def test_idempotent_same_locale(self) -> None:
        """Повторный вызов с той же локалью — entity без изменений."""
        use_case, players, audit, _, _ = _build_use_case()
        seeded = _seed_player(players, tg_id=42, locale_override="en")
        original_updated_at = seeded.updated_at

        result = await use_case.execute(tg_id=42, locale=Locale(code="en"))

        assert result.locale_override == "en"
        # Entity (updated_at) не должна меняться при no-op-е.
        assert players.rows[0].updated_at == original_updated_at
        # Audit всё равно пишется (нужен для счётчика «жмут /lang en»).
        assert len(audit.entries) == 1

    async def test_unregistered_player_raises(self) -> None:
        use_case, players, audit, uow, _ = _build_use_case()
        # Никого не подкладывали.

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(tg_id=999, locale=Locale(code="ru"))

        assert players.rows == []
        assert audit.entries == []
        # Транзакция всё равно открывалась — должна откатиться.
        assert uow.commits == 0
        assert uow.rollbacks == 1

    async def test_unsupported_locale_raises_value_error(self) -> None:
        use_case, players, audit, uow, _ = _build_use_case()
        _seed_player(players, tg_id=42)

        with pytest.raises(ValueError, match="unsupported locale"):
            await use_case.execute(tg_id=42, locale=Locale(code="fr"))

        # Никаких side-effect-ов: транзакция вообще не открывалась.
        assert uow.commits == 0
        assert uow.rollbacks == 0
        assert audit.entries == []
        assert players.rows[0].locale_override is None
