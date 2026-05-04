"""Unit-тесты `GetProfile` (Спринт 1.1.E, ГДД §2.2).

Покрываем:

1. Игрок зарегистрирован → возвращается `ProfileView` с правильно
   рассчитанным `display_name` (по длине, через `IBalanceConfig`).
2. Игрока нет → возвращается `None`, transactions не разъезжаются.
3. После hot-reload балансовой таблицы (`/balance_reload`) тот же
   игрок получает новое название без рестарта use-case-а — это
   соответствует acceptance Спринта 1.1.8.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.player import GetProfile
from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.player import (
    Player,
    PlayerName,
    PlayerStatus,
    Thickness,
    Title,
)
from pipirik_wars.domain.player.value_objects import Length, Username
from tests.fakes import (
    FakeBalanceConfig,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import (
    build_valid_balance,
    valid_balance_payload,
)


def _seed_player(
    repo: FakePlayerRepository,
    *,
    tg_id: int = 100,
    length_cm: int = 47,
    title: Title | None = None,
    name: PlayerName | None = None,
) -> Player:
    """Подложить готового игрока минуя бизнес-логику регистрации."""
    player = Player(
        id=1,
        tg_id=tg_id,
        username=Username(value="alice"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=1),
        title=title,
        name=name,
        status=PlayerStatus.ACTIVE,
        created_at=datetime(2026, 5, 4, tzinfo=UTC),
        updated_at=datetime(2026, 5, 4, tzinfo=UTC),
    )
    repo.rows.append(player)
    return player


def _build_use_case(
    *,
    balance: FakeBalanceConfig | None = None,
) -> tuple[GetProfile, FakePlayerRepository, FakeUnitOfWork, FakeBalanceConfig]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    used_balance = balance or FakeBalanceConfig(build_valid_balance())
    use_case = GetProfile(uow=uow, players=players, balance=used_balance)
    return use_case, players, uow, used_balance


def _build_balance_with_one_range(name: str, version: int = 1) -> BalanceConfig:
    """Сбилдить валидный `BalanceConfig` с **одним** рядом display_names.

    Используем `model_validate(payload)` (а не прямой конструктор), чтобы
    pydantic корректно разрешил алиасы `from`/`to`.
    """
    payload = valid_balance_payload()
    payload["version"] = version
    payload["display_names"] = [{"from": 0, "to": None, "name": name}]
    return BalanceConfig.model_validate(payload)


@pytest.mark.asyncio
class TestGetProfile:
    async def test_returns_view_with_calculated_display_name(self) -> None:
        balance = FakeBalanceConfig(_build_balance_with_one_range("Бананчик"))
        use_case, players, _, _ = _build_use_case(balance=balance)
        _seed_player(players, tg_id=100, length_cm=47)

        view = await use_case.execute(tg_id=100)

        assert view is not None
        assert view.player.tg_id == 100
        assert view.display_name.value == "Бананчик"

    async def test_returns_none_for_unregistered(self) -> None:
        use_case, players, uow, _ = _build_use_case()
        # Никого не подкладывали — repo пуст.

        view = await use_case.execute(tg_id=999)

        assert view is None
        assert players.rows == []
        # Транзакция должна была закрыться чисто (commit, без exception).
        assert uow.commits == 1
        assert uow.rollbacks == 0

    async def test_full_player_card_includes_all_fields(self) -> None:
        balance = FakeBalanceConfig(_build_balance_with_one_range("Бананчик"))
        use_case, players, _, _ = _build_use_case(balance=balance)
        _seed_player(
            players,
            tg_id=100,
            length_cm=47,
            title=Title.NEWBIE,
            name=PlayerName(value="Коляндр"),
        )

        view = await use_case.execute(tg_id=100)

        assert view is not None
        assert view.player.title is Title.NEWBIE
        assert view.player.name is not None
        assert view.player.name.value == "Коляндр"

    async def test_display_name_changes_after_hot_reload(self) -> None:
        """Acceptance Спринта 1.1.8: после reload новое название применяется."""
        old_balance = _build_balance_with_one_range("Старое", version=1)
        new_balance = _build_balance_with_one_range("Новое", version=2)
        balance = FakeBalanceConfig(old_balance)
        use_case, players, _, _ = _build_use_case(balance=balance)
        _seed_player(players, tg_id=100, length_cm=47)

        before = await use_case.execute(tg_id=100)
        assert before is not None
        assert before.display_name.value == "Старое"

        # Имитация `/balance_reload`: новый снимок становится текущим.
        balance.set(new_balance)

        after = await use_case.execute(tg_id=100)
        assert after is not None
        assert after.display_name.value == "Новое"
        # Игрок при этом не пересоздаётся.
        assert after.player.id == before.player.id
