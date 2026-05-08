"""Unit-тесты `TelegramCaravanLobbyCloseNotifier` и
`TelegramCaravanBattleFinishNotifier` (Спринт 3.2-D, D.6/D.8).

Покрытие:
- идемпотентность (`was_already_closed` / `was_already_finished`);
- happy-path рассылки в чаты sender/receiver кланов;
- best-effort обработка ошибок (TelegramAPIError / RuntimeError /
  отсутствие клана / отсутствие лидера) — не падаем, не валим
  APScheduler-job;
- резолв локали через `IPlayerLocaleResolver` (RU/EN);
- battle-finish: ветка delivered (raiders_won=False) и raided
  (raiders_won=True) с подгрузкой Атамана.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import SendMessage

from pipirik_wars.application.caravans import (
    CaravanBattleFinished,
    ClosedCaravanLobby,
)
from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.notifications import (
    TelegramCaravanBattleFinishNotifier,
    TelegramCaravanLobbyCloseNotifier,
)
from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanParticipant,
    CaravanStatus,
)
from pipirik_wars.domain.caravan.services import (
    CaravanBattleResult,
    CaravanParticipantOutcome,
)
from pipirik_wars.domain.caravan.value_objects import CaravanContribution
from pipirik_wars.domain.clan import Clan, ClanStatus
from pipirik_wars.domain.clan.value_objects import ChatKind, ClanTitle
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerStatus,
    Thickness,
    Title,
    Username,
)
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import (
    FakeBalanceConfig,
    FakeCaravanParticipantRepository,
    FakeClanRepository,
    FakeMessageBundle,
    FakePlayerLocaleResolver,
    FakePlayerRepository,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_LOBBY_ENDS = _NOW + timedelta(minutes=20)
_BATTLE_ENDS = _LOBBY_ENDS + timedelta(minutes=60)


# --------------------------- fakes / fixtures ---------------------------


@dataclass
class _SendCall:
    chat_id: int | str
    text: str


@dataclass
class _FakeBot:
    """Минимальная замена `aiogram.Bot.send_message`."""

    calls: list[_SendCall] = field(default_factory=list)
    raise_exc: BaseException | None = None

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        **_kwargs: Any,
    ) -> None:
        self.calls.append(_SendCall(chat_id=chat_id, text=text))
        if self.raise_exc is not None:
            raise self.raise_exc


def _fluent_bundle() -> IMessageBundle:
    return FluentMessageBundle(locales_dir=Path(__file__).resolve().parents[4] / "locales")


def _player(*, player_id: int, tg_id: int, length_cm: int = 25) -> Player:
    return Player(
        id=player_id,
        tg_id=tg_id,
        username=Username(value=f"user{tg_id}"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=7),
        title=Title.NEWBIE,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _clan(*, clan_id: int, chat_id: int, title: str) -> Clan:
    return Clan(
        id=clan_id,
        chat_id=chat_id,
        chat_kind=ChatKind.SUPERGROUP,
        title=ClanTitle(value=title),
        status=ClanStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _caravan(*, caravan_id: int = 99, status: CaravanStatus = CaravanStatus.IN_BATTLE) -> Caravan:
    return Caravan(
        id=caravan_id,
        sender_clan_id=10,
        receiver_clan_id=20,
        leader_player_id=1,
        status=status,
        started_at=_NOW,
        lobby_ends_at=_LOBBY_ENDS,
        battle_ends_at=_BATTLE_ENDS,
        random_seed=42,
        finished_at=None,
    )


def _caravaneer(*, player_id: int, contribution_cm: int = 10) -> CaravanParticipant:
    return CaravanParticipant.caravaneer(
        caravan_id=99,
        player_id=player_id,
        contribution=CaravanContribution(cm=contribution_cm),
        is_leader=(player_id == 1),
        joined_at=_NOW,
    )


def _defender(*, player_id: int) -> CaravanParticipant:
    return CaravanParticipant.defender(caravan_id=99, player_id=player_id, joined_at=_NOW)


def _raider(*, player_id: int) -> CaravanParticipant:
    return CaravanParticipant.raider(caravan_id=99, player_id=player_id, joined_at=_NOW)


def _seed_world() -> tuple[
    FakeClanRepository,
    FakePlayerRepository,
    FakeCaravanParticipantRepository,
]:
    clans = FakeClanRepository(
        rows=[
            _clan(clan_id=10, chat_id=-100_111, title="Senders"),
            _clan(clan_id=20, chat_id=-100_222, title="Receivers"),
        ],
    )
    leader = _player(player_id=1, tg_id=1001, length_cm=30)
    co = _player(player_id=2, tg_id=1002, length_cm=25)
    deff = _player(player_id=3, tg_id=1003, length_cm=22)
    raider = _player(player_id=4, tg_id=1004, length_cm=28)
    players = FakePlayerRepository(rows=[leader, co, deff, raider])
    participants = FakeCaravanParticipantRepository(
        rows=[
            _caravaneer(player_id=1, contribution_cm=10),
            _caravaneer(player_id=2, contribution_cm=5),
            _defender(player_id=3),
            _raider(player_id=4),
        ],
    )
    return clans, players, participants


def _make_lobby_close_notifier(
    *,
    bot: _FakeBot,
    clans: FakeClanRepository | None = None,
    players: FakePlayerRepository | None = None,
    participants: FakeCaravanParticipantRepository | None = None,
    bundle: IMessageBundle | None = None,
    locale_resolver: FakePlayerLocaleResolver | None = None,
    default_locale: Locale | None = None,
    logger: logging.Logger | None = None,
) -> TelegramCaravanLobbyCloseNotifier:
    seeded_clans, seeded_players, seeded_participants = _seed_world()
    kwargs: dict[str, Any] = {
        "bot": cast(Bot, bot),
        "bundle": bundle if bundle is not None else _fluent_bundle(),
        "balance": FakeBalanceConfig(build_valid_balance()),
        "clans": clans if clans is not None else seeded_clans,
        "players": players if players is not None else seeded_players,
        "participants": participants if participants is not None else seeded_participants,
        "locale_resolver": locale_resolver,
        "logger": logger,
    }
    if default_locale is not None:
        kwargs["default_locale"] = default_locale
    return TelegramCaravanLobbyCloseNotifier(**kwargs)


def _make_battle_finish_notifier(
    *,
    bot: _FakeBot,
    clans: FakeClanRepository | None = None,
    players: FakePlayerRepository | None = None,
    participants: FakeCaravanParticipantRepository | None = None,
    bundle: IMessageBundle | None = None,
    locale_resolver: FakePlayerLocaleResolver | None = None,
    default_locale: Locale | None = None,
    logger: logging.Logger | None = None,
) -> TelegramCaravanBattleFinishNotifier:
    seeded_clans, seeded_players, seeded_participants = _seed_world()
    kwargs: dict[str, Any] = {
        "bot": cast(Bot, bot),
        "bundle": bundle if bundle is not None else _fluent_bundle(),
        "balance": FakeBalanceConfig(build_valid_balance()),
        "clans": clans if clans is not None else seeded_clans,
        "players": players if players is not None else seeded_players,
        "participants": participants if participants is not None else seeded_participants,
        "locale_resolver": locale_resolver,
        "logger": logger,
    }
    if default_locale is not None:
        kwargs["default_locale"] = default_locale
    return TelegramCaravanBattleFinishNotifier(**kwargs)


def _telegram_api_error() -> TelegramAPIError:
    method = SendMessage(chat_id=1, text="x")
    return TelegramAPIError(method=method, message="blocked")


# --------------------------- lobby-close notifier ---------------------------


@pytest.mark.asyncio
async def test_lobby_close_skips_when_was_already_closed() -> None:
    bot = _FakeBot()
    notifier = _make_lobby_close_notifier(bot=bot)
    await notifier.notify(
        ClosedCaravanLobby(
            caravan=_caravan(status=CaravanStatus.IN_BATTLE),
            was_already_closed=True,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_lobby_close_sends_to_both_clan_chats_default_en() -> None:
    bot = _FakeBot()
    notifier = _make_lobby_close_notifier(bot=bot)
    await notifier.notify(ClosedCaravanLobby(caravan=_caravan(), was_already_closed=False))
    chat_ids = sorted(c.chat_id for c in bot.calls)
    assert chat_ids == [-100_222, -100_111]
    # Один и тот же текст ушёл обоим кланам (mass-broadcast в чаты).
    assert bot.calls[0].text == bot.calls[1].text
    # EN-фразы должны попасть (default DEFAULT_LOCALE = en).
    assert "battle has begun" in bot.calls[0].text.lower() or "battle" in bot.calls[0].text.lower()


@pytest.mark.asyncio
async def test_lobby_close_renders_in_player_locale_ru() -> None:
    bot = _FakeBot()
    resolver = FakePlayerLocaleResolver()
    resolver.set_override(1001, Locale("ru"))
    notifier = _make_lobby_close_notifier(
        bot=bot,
        locale_resolver=resolver,
        default_locale=Locale("en"),
    )
    await notifier.notify(ClosedCaravanLobby(caravan=_caravan(), was_already_closed=False))
    assert len(bot.calls) == 2
    # Не должно быть EN-фраз, должны быть RU-фразы.
    assert "Караван" in bot.calls[0].text or "караван" in bot.calls[0].text
    assert resolver.calls == [1001]


@pytest.mark.asyncio
async def test_lobby_close_skips_when_caravan_id_is_none() -> None:
    bot = _FakeBot()
    notifier = _make_lobby_close_notifier(bot=bot)
    naked = Caravan(
        id=None,
        sender_clan_id=10,
        receiver_clan_id=20,
        leader_player_id=1,
        status=CaravanStatus.IN_BATTLE,
        started_at=_NOW,
        lobby_ends_at=_LOBBY_ENDS,
        battle_ends_at=_BATTLE_ENDS,
        random_seed=42,
        finished_at=None,
    )
    await notifier.notify(ClosedCaravanLobby(caravan=naked, was_already_closed=False))
    assert bot.calls == []


@pytest.mark.asyncio
async def test_lobby_close_skips_when_sender_clan_missing() -> None:
    bot = _FakeBot()
    # Только receiver — sender пропал.
    clans = FakeClanRepository(rows=[_clan(clan_id=20, chat_id=-100_222, title="Receivers")])
    notifier = _make_lobby_close_notifier(bot=bot, clans=clans)
    await notifier.notify(ClosedCaravanLobby(caravan=_caravan(), was_already_closed=False))
    assert bot.calls == []


@pytest.mark.asyncio
async def test_lobby_close_skips_when_leader_missing() -> None:
    bot = _FakeBot()
    # Лидер не существует в БД (id=1 отсутствует).
    players = FakePlayerRepository(rows=[_player(player_id=2, tg_id=1002)])
    notifier = _make_lobby_close_notifier(bot=bot, players=players)
    await notifier.notify(ClosedCaravanLobby(caravan=_caravan(), was_already_closed=False))
    assert bot.calls == []


@pytest.mark.asyncio
async def test_lobby_close_swallows_telegram_api_error() -> None:
    bot = _FakeBot(raise_exc=_telegram_api_error())
    notifier = _make_lobby_close_notifier(bot=bot)
    # Не должно бросить — best-effort контракт.
    await notifier.notify(ClosedCaravanLobby(caravan=_caravan(), was_already_closed=False))
    # Оба send-а попытались (не упали при первом — продолжили со вторым).
    assert len(bot.calls) == 2


@pytest.mark.asyncio
async def test_lobby_close_swallows_unexpected_error() -> None:
    bot = _FakeBot(raise_exc=RuntimeError("network down"))
    notifier = _make_lobby_close_notifier(bot=bot)
    await notifier.notify(ClosedCaravanLobby(caravan=_caravan(), was_already_closed=False))


@pytest.mark.asyncio
async def test_lobby_close_uses_marker_bundle_for_battle_started_key() -> None:
    bot = _FakeBot()
    notifier = _make_lobby_close_notifier(
        bot=bot,
        bundle=FakeMessageBundle(),
        default_locale=Locale("en"),
    )
    await notifier.notify(ClosedCaravanLobby(caravan=_caravan(), was_already_closed=False))
    # Маркерный bundle гарантирует, что нотификатор просит ключ
    # `caravans-battle-started` (а не любой другой).
    assert "en:caravans-battle-started" in bot.calls[0].text


# --------------------------- battle-finish notifier ---------------------------


def _outcomes_delivered() -> tuple[CaravanParticipantOutcome, ...]:
    """Победили караванщики: лидер + 1 караванщик + защитник живы, рейдер — нет (но `is_alive=True`)."""
    return (
        CaravanParticipantOutcome(
            participant=_caravaneer(player_id=1, contribution_cm=10),
            is_alive=True,
            length_delta_cm=40,
            gets_ataman_title=False,
        ),
        CaravanParticipantOutcome(
            participant=_caravaneer(player_id=2, contribution_cm=5),
            is_alive=True,
            length_delta_cm=15,
            gets_ataman_title=False,
        ),
        CaravanParticipantOutcome(
            participant=_defender(player_id=3),
            is_alive=True,
            length_delta_cm=5,
            gets_ataman_title=False,
        ),
        CaravanParticipantOutcome(
            participant=_raider(player_id=4),
            is_alive=True,
            length_delta_cm=-1,
            gets_ataman_title=False,
        ),
    )


def _outcomes_raided() -> tuple[CaravanParticipantOutcome, ...]:
    """Победили рейдеры: оба караванщика и защитник мертвы; рейдер — Атаман."""
    return (
        CaravanParticipantOutcome(
            participant=_caravaneer(player_id=1, contribution_cm=10),
            is_alive=False,
            length_delta_cm=-3,
            gets_ataman_title=False,
        ),
        CaravanParticipantOutcome(
            participant=_caravaneer(player_id=2, contribution_cm=5),
            is_alive=False,
            length_delta_cm=-3,
            gets_ataman_title=False,
        ),
        CaravanParticipantOutcome(
            participant=_defender(player_id=3),
            is_alive=False,
            length_delta_cm=-3,
            gets_ataman_title=False,
        ),
        CaravanParticipantOutcome(
            participant=_raider(player_id=4),
            is_alive=True,
            length_delta_cm=20,
            gets_ataman_title=True,
        ),
    )


def _result_delivered() -> CaravanBattleResult:
    return CaravanBattleResult(
        raiders_won=False,
        participant_outcomes=_outcomes_delivered(),
        clan_bonus_cm_sender=1,
        clan_bonus_cm_receiver=1,
    )


def _result_raided() -> CaravanBattleResult:
    return CaravanBattleResult(
        raiders_won=True,
        participant_outcomes=_outcomes_raided(),
        clan_bonus_cm_sender=0,
        clan_bonus_cm_receiver=0,
    )


@pytest.mark.asyncio
async def test_battle_finish_skips_when_already_finished() -> None:
    bot = _FakeBot()
    notifier = _make_battle_finish_notifier(bot=bot)
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=None,
            was_already_finished=True,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_battle_finish_skips_when_result_is_none() -> None:
    """Контракт application-слоя: `result is None` — no-op путь use-case-а."""
    bot = _FakeBot()
    notifier = _make_battle_finish_notifier(bot=bot)
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=None,
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_battle_finish_delivered_sends_to_both_clan_chats() -> None:
    bot = _FakeBot()
    notifier = _make_battle_finish_notifier(bot=bot)
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=_result_delivered(),
            was_already_finished=False,
        )
    )
    chat_ids = sorted(c.chat_id for c in bot.calls)
    assert chat_ids == [-100_222, -100_111]
    assert bot.calls[0].text == bot.calls[1].text


@pytest.mark.asyncio
async def test_battle_finish_delivered_uses_marker_key() -> None:
    bot = _FakeBot()
    notifier = _make_battle_finish_notifier(
        bot=bot,
        bundle=FakeMessageBundle(),
        default_locale=Locale("en"),
    )
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=_result_delivered(),
            was_already_finished=False,
        )
    )
    assert "en:caravans-battle-finished-delivered" in bot.calls[0].text


@pytest.mark.asyncio
async def test_battle_finish_raided_uses_marker_key_and_resolves_ataman() -> None:
    bot = _FakeBot()
    notifier = _make_battle_finish_notifier(
        bot=bot,
        bundle=FakeMessageBundle(),
        default_locale=Locale("en"),
    )
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=_result_raided(),
            was_already_finished=False,
        )
    )
    assert "en:caravans-battle-finished-raided" in bot.calls[0].text


@pytest.mark.asyncio
async def test_battle_finish_raided_when_ataman_player_missing_still_sends() -> None:
    """Если Атаман-игрок не нашёлся в БД, презентер рендерит «—» —
    сообщения всё равно уходят (best-effort)."""
    bot = _FakeBot()
    # Лидер есть (id=1), но рейдера-Атамана (id=4) нет — он удалён.
    players = FakePlayerRepository(
        rows=[
            _player(player_id=1, tg_id=1001, length_cm=30),
            _player(player_id=2, tg_id=1002, length_cm=25),
            _player(player_id=3, tg_id=1003, length_cm=22),
        ]
    )
    notifier = _make_battle_finish_notifier(bot=bot, players=players)
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=_result_raided(),
            was_already_finished=False,
        )
    )
    assert len(bot.calls) == 2
    # Прочерк для отсутствующего Атамана попадает в текст.
    assert "—" in bot.calls[0].text


@pytest.mark.asyncio
async def test_battle_finish_renders_in_player_locale_ru() -> None:
    bot = _FakeBot()
    resolver = FakePlayerLocaleResolver()
    resolver.set_override(1001, Locale("ru"))
    notifier = _make_battle_finish_notifier(
        bot=bot,
        locale_resolver=resolver,
        default_locale=Locale("en"),
    )
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=_result_delivered(),
            was_already_finished=False,
        )
    )
    assert len(bot.calls) == 2
    # RU-маркерные слова: «доставлен» / «караван».
    assert (
        "доставлен" in bot.calls[0].text
        or "Караван" in bot.calls[0].text
        or "караван" in bot.calls[0].text
    )
    assert resolver.calls == [1001]


@pytest.mark.asyncio
async def test_battle_finish_skips_when_caravan_id_is_none() -> None:
    bot = _FakeBot()
    notifier = _make_battle_finish_notifier(bot=bot)
    naked = Caravan(
        id=None,
        sender_clan_id=10,
        receiver_clan_id=20,
        leader_player_id=1,
        status=CaravanStatus.FINISHED,
        started_at=_NOW,
        lobby_ends_at=_LOBBY_ENDS,
        battle_ends_at=_BATTLE_ENDS,
        random_seed=42,
        finished_at=_NOW,
    )
    await notifier.notify(
        CaravanBattleFinished(
            caravan=naked,
            result=_result_delivered(),
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_battle_finish_skips_when_clan_missing() -> None:
    bot = _FakeBot()
    clans = FakeClanRepository(rows=[_clan(clan_id=10, chat_id=-100_111, title="Senders")])
    notifier = _make_battle_finish_notifier(bot=bot, clans=clans)
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=_result_delivered(),
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_battle_finish_skips_when_leader_missing() -> None:
    bot = _FakeBot()
    players = FakePlayerRepository(rows=[_player(player_id=2, tg_id=1002)])
    notifier = _make_battle_finish_notifier(bot=bot, players=players)
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=_result_delivered(),
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_battle_finish_swallows_telegram_api_error() -> None:
    bot = _FakeBot(raise_exc=_telegram_api_error())
    notifier = _make_battle_finish_notifier(bot=bot)
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=_result_delivered(),
            was_already_finished=False,
        )
    )
    assert len(bot.calls) == 2


@pytest.mark.asyncio
async def test_battle_finish_swallows_unexpected_error() -> None:
    bot = _FakeBot(raise_exc=RuntimeError("network down"))
    notifier = _make_battle_finish_notifier(bot=bot)
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=_result_delivered(),
            was_already_finished=False,
        )
    )


@pytest.mark.asyncio
async def test_locale_resolver_swallows_errors() -> None:
    """Если резолвер локали упал — фолбэк на default_locale, ничего не падает."""
    bot = _FakeBot()

    @dataclass
    class _BoomResolver:
        async def resolve_for_tg_id(self, tg_id: int) -> Locale | None:
            raise RuntimeError("db down")

    notifier = _make_battle_finish_notifier(
        bot=bot,
        locale_resolver=cast(Any, _BoomResolver()),
        default_locale=Locale("en"),
    )
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=_result_delivered(),
            was_already_finished=False,
        )
    )
    assert len(bot.calls) == 2


@pytest.mark.asyncio
async def test_battle_finish_uses_default_logger_when_none_provided() -> None:
    bot = _FakeBot()
    seeded_clans, seeded_players, seeded_participants = _seed_world()
    notifier = TelegramCaravanBattleFinishNotifier(
        bot=cast(Bot, bot),
        bundle=_fluent_bundle(),
        balance=FakeBalanceConfig(build_valid_balance()),
        clans=seeded_clans,
        players=seeded_players,
        participants=seeded_participants,
    )
    await notifier.notify(
        CaravanBattleFinished(
            caravan=_caravan(status=CaravanStatus.FINISHED),
            result=_result_delivered(),
            was_already_finished=False,
        )
    )
    assert len(bot.calls) == 2
