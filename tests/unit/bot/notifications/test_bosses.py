"""Unit-тесты `TelegramBossLobbyCloseNotifier` /
`TelegramBossRoundTickNotifier` / `TelegramBossFightFinishNotifier`
(Спринт 3.3-D, D.7 / D.11b).

Покрытие:
- идемпотентность (`was_already_closed` / `was_already_finished`);
- happy-path рассылки в личные чаты живых рейдеров и босса;
- best-effort обработка ошибок (TelegramAPIError / RuntimeError /
  отсутствие игроков / падение репо) — не падаем, не валим
  APScheduler-job;
- резолв локали через `IPlayerLocaleResolver` (RU/EN);
- round-tick: ветка с участниками + пустой список = no-op;
- fight-finish: ветка victory (`raiders_won=True`) и defeat
  (`raiders_won=False`); отдельная доставка боссу и саммонеру,
  если он выбит из `participants`.
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

from pipirik_wars.application.bosses import (
    BossFightFinished,
    BossLobbyClosed,
    BossRoundResolved,
)
from pipirik_wars.application.i18n import IMessageBundle, IPlayerLocaleResolver, Locale
from pipirik_wars.bot.notifications import (
    TelegramBossFightFinishNotifier,
    TelegramBossLobbyCloseNotifier,
    TelegramBossRoundTickNotifier,
)
from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightStatus,
    BossKind,
    BossParticipant,
)
from pipirik_wars.domain.bosses.services import (
    BossRaiderRoundOutcome,
    BossRoundResult,
)
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
    FakeBossParticipantRepository,
    FakeMessageBundle,
    FakePlayerLocaleResolver,
    FakePlayerRepository,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_LOBBY_ENDS = _NOW + timedelta(minutes=20)


# --------------------------- fakes / fixtures ---------------------------


@dataclass
class _SendCall:
    chat_id: int | str
    text: str


@dataclass
class _FakeBot:
    """Минимальная замена `aiogram.Bot.send_message` (мирится с per-call ошибкой)."""

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


def _player(
    *,
    player_id: int,
    tg_id: int,
    length_cm: int = 25,
    thickness_level: int = 7,
) -> Player:
    return Player(
        id=player_id,
        tg_id=tg_id,
        username=Username(value=f"user{tg_id}"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=thickness_level),
        title=Title.NEWBIE,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _boss_fight(
    *,
    boss_fight_id: int | None = 99,
    status: BossFightStatus = BossFightStatus.IN_BATTLE,
    summoner_player_id: int = 1,
    boss_player_id: int = 2,
    initial_boss_length_cm: int = 100,
    current_boss_length_cm: int | None = None,
    current_round: int = 0,
) -> BossFight:
    return BossFight(
        id=boss_fight_id,
        kind=BossKind.RAID,
        summoner_player_id=summoner_player_id,
        boss_player_id=boss_player_id,
        status=status,
        started_at=_NOW,
        lobby_ends_at=_LOBBY_ENDS,
        finished_at=None,
        random_seed=42,
        initial_boss_length_cm=initial_boss_length_cm,
        current_boss_length_cm=current_boss_length_cm
        if current_boss_length_cm is not None
        else initial_boss_length_cm,
        current_round=current_round,
    )


def _summoner(*, player_id: int = 1, boss_fight_id: int = 99) -> BossParticipant:
    return BossParticipant(
        boss_fight_id=boss_fight_id,
        player_id=player_id,
        is_summoner=True,
        length_at_join_cm=30,
        joined_at=_NOW,
    )


def _raider(*, player_id: int, boss_fight_id: int = 99) -> BossParticipant:
    return BossParticipant(
        boss_fight_id=boss_fight_id,
        player_id=player_id,
        is_summoner=False,
        length_at_join_cm=25,
        joined_at=_NOW,
    )


def _seed_world() -> tuple[FakePlayerRepository, FakeBossParticipantRepository]:
    """3 рейдера (id=1 саммонер + id=3, id=4) + босс (id=2)."""
    summoner = _player(player_id=1, tg_id=1001, length_cm=30)
    boss = _player(player_id=2, tg_id=2002, length_cm=80)
    raider3 = _player(player_id=3, tg_id=3003, length_cm=25)
    raider4 = _player(player_id=4, tg_id=4004, length_cm=22)
    players = FakePlayerRepository(rows=[summoner, boss, raider3, raider4])
    participants = FakeBossParticipantRepository(
        rows=[
            _summoner(player_id=1, boss_fight_id=99),
            _raider(player_id=3, boss_fight_id=99),
            _raider(player_id=4, boss_fight_id=99),
        ],
    )
    return players, participants


def _make_lobby_close_notifier(
    *,
    bot: _FakeBot,
    players: FakePlayerRepository | None = None,
    participants: FakeBossParticipantRepository | None = None,
    bundle: IMessageBundle | None = None,
    locale_resolver: IPlayerLocaleResolver | None = None,
    default_locale: Locale | None = None,
    logger: logging.Logger | None = None,
) -> TelegramBossLobbyCloseNotifier:
    seeded_players, seeded_participants = _seed_world()
    kwargs: dict[str, Any] = {
        "bot": cast(Bot, bot),
        "bundle": bundle if bundle is not None else _fluent_bundle(),
        "balance": FakeBalanceConfig(build_valid_balance()),
        "players": players if players is not None else seeded_players,
        "participants": participants if participants is not None else seeded_participants,
        "locale_resolver": locale_resolver,
        "logger": logger,
    }
    if default_locale is not None:
        kwargs["default_locale"] = default_locale
    return TelegramBossLobbyCloseNotifier(**kwargs)


def _make_round_tick_notifier(
    *,
    bot: _FakeBot,
    players: FakePlayerRepository | None = None,
    participants: FakeBossParticipantRepository | None = None,
    bundle: IMessageBundle | None = None,
    locale_resolver: IPlayerLocaleResolver | None = None,
    default_locale: Locale | None = None,
    logger: logging.Logger | None = None,
) -> TelegramBossRoundTickNotifier:
    seeded_players, seeded_participants = _seed_world()
    kwargs: dict[str, Any] = {
        "bot": cast(Bot, bot),
        "bundle": bundle if bundle is not None else _fluent_bundle(),
        "balance": FakeBalanceConfig(build_valid_balance()),
        "players": players if players is not None else seeded_players,
        "participants": participants if participants is not None else seeded_participants,
        "locale_resolver": locale_resolver,
        "logger": logger,
    }
    if default_locale is not None:
        kwargs["default_locale"] = default_locale
    return TelegramBossRoundTickNotifier(**kwargs)


def _make_fight_finish_notifier(
    *,
    bot: _FakeBot,
    players: FakePlayerRepository | None = None,
    participants: FakeBossParticipantRepository | None = None,
    bundle: IMessageBundle | None = None,
    locale_resolver: IPlayerLocaleResolver | None = None,
    default_locale: Locale | None = None,
    logger: logging.Logger | None = None,
) -> TelegramBossFightFinishNotifier:
    seeded_players, seeded_participants = _seed_world()
    kwargs: dict[str, Any] = {
        "bot": cast(Bot, bot),
        "bundle": bundle if bundle is not None else _fluent_bundle(),
        "balance": FakeBalanceConfig(build_valid_balance()),
        "players": players if players is not None else seeded_players,
        "participants": participants if participants is not None else seeded_participants,
        "locale_resolver": locale_resolver,
        "logger": logger,
    }
    if default_locale is not None:
        kwargs["default_locale"] = default_locale
    return TelegramBossFightFinishNotifier(**kwargs)


def _telegram_api_error() -> TelegramAPIError:
    method = SendMessage(chat_id=1, text="x")
    return TelegramAPIError(method=method, message="blocked")


# --------------------------- lobby-close notifier ---------------------------


@pytest.mark.asyncio
async def test_lobby_close_skips_when_was_already_closed() -> None:
    bot = _FakeBot()
    notifier = _make_lobby_close_notifier(bot=bot)
    await notifier.notify(
        BossLobbyClosed(
            boss_fight=_boss_fight(status=BossFightStatus.IN_BATTLE),
            was_already_closed=True,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_lobby_close_skips_when_boss_fight_id_is_none() -> None:
    bot = _FakeBot()
    notifier = _make_lobby_close_notifier(bot=bot)
    await notifier.notify(
        BossLobbyClosed(
            boss_fight=_boss_fight(boss_fight_id=None),
            was_already_closed=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_lobby_close_sends_to_all_raiders_default_en() -> None:
    bot = _FakeBot()
    notifier = _make_lobby_close_notifier(bot=bot)
    await notifier.notify(
        BossLobbyClosed(
            boss_fight=_boss_fight(),
            was_already_closed=False,
        )
    )
    chat_ids = sorted(c.chat_id for c in bot.calls)
    # 3 рейдера: саммонер 1001 + рейдеры 3003, 4004.
    assert chat_ids == [1001, 3003, 4004]
    # Тексты могут различаться (рендер на одинаковую локаль = одинаковый текст).
    assert bot.calls[0].text == bot.calls[1].text == bot.calls[2].text


@pytest.mark.asyncio
async def test_lobby_close_uses_marker_bundle_for_battle_started_key() -> None:
    bot = _FakeBot()
    notifier = _make_lobby_close_notifier(
        bot=bot,
        bundle=FakeMessageBundle(),
        default_locale=Locale("en"),
    )
    await notifier.notify(
        BossLobbyClosed(
            boss_fight=_boss_fight(),
            was_already_closed=False,
        )
    )
    assert all("en:bosses-battle-started" in c.text for c in bot.calls)


@pytest.mark.asyncio
async def test_lobby_close_renders_in_player_locale_ru() -> None:
    bot = _FakeBot()
    resolver = FakePlayerLocaleResolver()
    resolver.set_override(1001, Locale("ru"))
    notifier = _make_lobby_close_notifier(
        bot=bot,
        bundle=FakeMessageBundle(),
        locale_resolver=resolver,
        default_locale=Locale("en"),
    )
    await notifier.notify(
        BossLobbyClosed(
            boss_fight=_boss_fight(),
            was_already_closed=False,
        )
    )
    by_chat = {c.chat_id: c.text for c in bot.calls}
    assert "ru:bosses-battle-started" in by_chat[1001]
    assert "en:bosses-battle-started" in by_chat[3003]
    assert "en:bosses-battle-started" in by_chat[4004]


@pytest.mark.asyncio
async def test_lobby_close_skips_when_summoner_player_missing() -> None:
    bot = _FakeBot()
    # Саммонер id=1 отсутствует в репо.
    players = FakePlayerRepository(
        rows=[
            _player(player_id=2, tg_id=2002, length_cm=80),
            _player(player_id=3, tg_id=3003),
            _player(player_id=4, tg_id=4004),
        ]
    )
    notifier = _make_lobby_close_notifier(bot=bot, players=players)
    await notifier.notify(BossLobbyClosed(boss_fight=_boss_fight(), was_already_closed=False))
    assert bot.calls == []


@pytest.mark.asyncio
async def test_lobby_close_skips_when_boss_player_missing() -> None:
    bot = _FakeBot()
    # Босс id=2 отсутствует в репо.
    players = FakePlayerRepository(
        rows=[
            _player(player_id=1, tg_id=1001, length_cm=30),
            _player(player_id=3, tg_id=3003),
            _player(player_id=4, tg_id=4004),
        ]
    )
    notifier = _make_lobby_close_notifier(bot=bot, players=players)
    await notifier.notify(BossLobbyClosed(boss_fight=_boss_fight(), was_already_closed=False))
    assert bot.calls == []


@pytest.mark.asyncio
async def test_lobby_close_skips_specific_raider_when_player_missing() -> None:
    """Если один из рейдеров пропал из БД — пропускаем только его."""
    bot = _FakeBot()
    # Рейдер id=3 пропал.
    players = FakePlayerRepository(
        rows=[
            _player(player_id=1, tg_id=1001, length_cm=30),
            _player(player_id=2, tg_id=2002, length_cm=80),
            _player(player_id=4, tg_id=4004),
        ]
    )
    notifier = _make_lobby_close_notifier(bot=bot, players=players)
    await notifier.notify(BossLobbyClosed(boss_fight=_boss_fight(), was_already_closed=False))
    chat_ids = sorted(c.chat_id for c in bot.calls)
    assert chat_ids == [1001, 4004]


@pytest.mark.asyncio
async def test_lobby_close_swallows_telegram_api_error() -> None:
    bot = _FakeBot(raise_exc=_telegram_api_error())
    notifier = _make_lobby_close_notifier(bot=bot)
    # Не должно бросить — best-effort контракт.
    await notifier.notify(BossLobbyClosed(boss_fight=_boss_fight(), was_already_closed=False))
    # Все 3 send-а попробовались (не упали при первом — продолжили).
    assert len(bot.calls) == 3


@pytest.mark.asyncio
async def test_lobby_close_swallows_unexpected_error() -> None:
    bot = _FakeBot(raise_exc=RuntimeError("network down"))
    notifier = _make_lobby_close_notifier(bot=bot)
    await notifier.notify(BossLobbyClosed(boss_fight=_boss_fight(), was_already_closed=False))
    assert len(bot.calls) == 3


@pytest.mark.asyncio
async def test_lobby_close_swallows_participants_repo_error() -> None:
    bot = _FakeBot()

    class _BoomParticipants(FakeBossParticipantRepository):
        async def list_by_boss_fight(self, *, boss_fight_id: int) -> tuple[BossParticipant, ...]:
            raise RuntimeError("db down")

    notifier = _make_lobby_close_notifier(bot=bot, participants=_BoomParticipants())
    await notifier.notify(BossLobbyClosed(boss_fight=_boss_fight(), was_already_closed=False))
    assert bot.calls == []


# --------------------------- round-tick notifier ---------------------------


def _round_outcomes(
    eliminated_player_ids: tuple[int, ...] = (),
) -> tuple[BossRaiderRoundOutcome, ...]:
    """Per-raider outcomes (саммонер + 2 рейдера). Eliminated — по id."""
    return tuple(
        BossRaiderRoundOutcome(
            participant=(_summoner(player_id=p_id) if p_id == 1 else _raider(player_id=p_id)),
            is_eliminated=p_id in eliminated_player_ids,
            damage_taken_cm=5 if p_id in eliminated_player_ids else 0,
        )
        for p_id in (1, 3, 4)
    )


def _round_result(
    *,
    boss_damage_cm: int = 15,
    eliminated_player_ids: tuple[int, ...] = (),
) -> BossRoundResult:
    return BossRoundResult(
        raider_outcomes=_round_outcomes(eliminated_player_ids),
        boss_damage_taken_cm=boss_damage_cm,
        eliminated_player_ids=eliminated_player_ids,
    )


@pytest.mark.asyncio
async def test_round_tick_skips_when_was_already_finished() -> None:
    bot = _FakeBot()
    notifier = _make_round_tick_notifier(bot=bot)
    await notifier.notify(
        BossRoundResolved(
            boss_fight=_boss_fight(status=BossFightStatus.FINISHED),
            result=None,
            is_finished=True,
            was_already_finished=True,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_round_tick_skips_when_result_is_none() -> None:
    """Контракт application: `result is None` — corner-case alive_raiders=∅."""
    bot = _FakeBot()
    notifier = _make_round_tick_notifier(bot=bot)
    await notifier.notify(
        BossRoundResolved(
            boss_fight=_boss_fight(),
            result=None,
            is_finished=False,
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_round_tick_skips_when_boss_fight_id_is_none() -> None:
    bot = _FakeBot()
    notifier = _make_round_tick_notifier(bot=bot)
    await notifier.notify(
        BossRoundResolved(
            boss_fight=_boss_fight(boss_fight_id=None),
            result=_round_result(),
            is_finished=False,
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_round_tick_sends_to_alive_raiders_default_en() -> None:
    bot = _FakeBot()
    notifier = _make_round_tick_notifier(bot=bot)
    await notifier.notify(
        BossRoundResolved(
            boss_fight=_boss_fight(current_boss_length_cm=85, current_round=1),
            result=_round_result(boss_damage_cm=15),
            is_finished=False,
            was_already_finished=False,
        )
    )
    chat_ids = sorted(c.chat_id for c in bot.calls)
    # Все 3 рейдера в `participants` живы.
    assert chat_ids == [1001, 3003, 4004]


@pytest.mark.asyncio
async def test_round_tick_uses_marker_bundle_for_round_tick_key() -> None:
    bot = _FakeBot()
    notifier = _make_round_tick_notifier(
        bot=bot,
        bundle=FakeMessageBundle(),
        default_locale=Locale("en"),
    )
    await notifier.notify(
        BossRoundResolved(
            boss_fight=_boss_fight(current_boss_length_cm=85, current_round=2),
            result=_round_result(boss_damage_cm=15),
            is_finished=False,
            was_already_finished=False,
        )
    )
    assert all("en:bosses-round-tick" in c.text for c in bot.calls)


@pytest.mark.asyncio
async def test_round_tick_skips_when_participants_empty() -> None:
    """Все рейдеры выбыли — финал придёт через FightFinishNotifier."""
    bot = _FakeBot()
    notifier = _make_round_tick_notifier(
        bot=bot,
        participants=FakeBossParticipantRepository(rows=[]),
    )
    await notifier.notify(
        BossRoundResolved(
            boss_fight=_boss_fight(),
            result=_round_result(),
            is_finished=False,
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_round_tick_skips_when_boss_player_missing() -> None:
    bot = _FakeBot()
    players = FakePlayerRepository(
        rows=[
            _player(player_id=1, tg_id=1001, length_cm=30),
            _player(player_id=3, tg_id=3003),
            _player(player_id=4, tg_id=4004),
        ]
    )
    notifier = _make_round_tick_notifier(bot=bot, players=players)
    await notifier.notify(
        BossRoundResolved(
            boss_fight=_boss_fight(),
            result=_round_result(),
            is_finished=False,
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_round_tick_swallows_participants_repo_error() -> None:
    bot = _FakeBot()

    class _BoomParticipants(FakeBossParticipantRepository):
        async def list_by_boss_fight(self, *, boss_fight_id: int) -> tuple[BossParticipant, ...]:
            raise RuntimeError("db down")

    notifier = _make_round_tick_notifier(bot=bot, participants=_BoomParticipants())
    await notifier.notify(
        BossRoundResolved(
            boss_fight=_boss_fight(),
            result=_round_result(),
            is_finished=False,
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_round_tick_swallows_telegram_api_error() -> None:
    bot = _FakeBot(raise_exc=_telegram_api_error())
    notifier = _make_round_tick_notifier(bot=bot)
    await notifier.notify(
        BossRoundResolved(
            boss_fight=_boss_fight(),
            result=_round_result(),
            is_finished=False,
            was_already_finished=False,
        )
    )
    # Все 3 send-а попробовались.
    assert len(bot.calls) == 3


@pytest.mark.asyncio
async def test_round_tick_renders_in_player_locale_ru() -> None:
    bot = _FakeBot()
    resolver = FakePlayerLocaleResolver()
    resolver.set_override(3003, Locale("ru"))
    notifier = _make_round_tick_notifier(
        bot=bot,
        bundle=FakeMessageBundle(),
        locale_resolver=resolver,
        default_locale=Locale("en"),
    )
    await notifier.notify(
        BossRoundResolved(
            boss_fight=_boss_fight(),
            result=_round_result(),
            is_finished=False,
            was_already_finished=False,
        )
    )
    by_chat = {c.chat_id: c.text for c in bot.calls}
    assert "ru:bosses-round-tick" in by_chat[3003]
    assert "en:bosses-round-tick" in by_chat[1001]
    assert "en:bosses-round-tick" in by_chat[4004]


# --------------------------- fight-finish notifier ---------------------------


@pytest.mark.asyncio
async def test_fight_finish_skips_when_was_already_finished() -> None:
    bot = _FakeBot()
    notifier = _make_fight_finish_notifier(bot=bot)
    await notifier.notify(
        BossFightFinished(
            boss_fight=_boss_fight(status=BossFightStatus.FINISHED),
            raiders_won=None,
            total_granted_cm=0,
            boss_revoked_cm=0,
            raiders_revoked_cm=0,
            scroll_drops=(),
            was_already_finished=True,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_fight_finish_skips_when_raiders_won_is_none() -> None:
    """Контракт: `raiders_won is None` — no-op путь use-case-а."""
    bot = _FakeBot()
    notifier = _make_fight_finish_notifier(bot=bot)
    await notifier.notify(
        BossFightFinished(
            boss_fight=_boss_fight(status=BossFightStatus.FINISHED),
            raiders_won=None,
            total_granted_cm=0,
            boss_revoked_cm=0,
            raiders_revoked_cm=0,
            scroll_drops=(),
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_fight_finish_skips_when_boss_fight_id_is_none() -> None:
    bot = _FakeBot()
    notifier = _make_fight_finish_notifier(bot=bot)
    await notifier.notify(
        BossFightFinished(
            boss_fight=_boss_fight(boss_fight_id=None),
            raiders_won=True,
            total_granted_cm=100,
            boss_revoked_cm=100,
            raiders_revoked_cm=0,
            scroll_drops=(),
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_fight_finish_victory_uses_marker_key_for_all_recipients() -> None:
    """Victory: 3 рейдера + босс получили `bosses-battle-finished-victory`."""
    bot = _FakeBot()
    notifier = _make_fight_finish_notifier(
        bot=bot,
        bundle=FakeMessageBundle(),
        default_locale=Locale("en"),
    )
    await notifier.notify(
        BossFightFinished(
            boss_fight=_boss_fight(status=BossFightStatus.FINISHED),
            raiders_won=True,
            total_granted_cm=100,
            boss_revoked_cm=100,
            raiders_revoked_cm=0,
            scroll_drops=(),
            was_already_finished=False,
        )
    )
    chat_ids = sorted(c.chat_id for c in bot.calls)
    # 3 рейдера + босс (4 уникальных получателя).
    assert chat_ids == [1001, 2002, 3003, 4004]
    assert all("en:bosses-battle-finished-victory" in c.text for c in bot.calls)


@pytest.mark.asyncio
async def test_fight_finish_defeat_uses_marker_key_for_all_recipients() -> None:
    bot = _FakeBot()
    notifier = _make_fight_finish_notifier(
        bot=bot,
        bundle=FakeMessageBundle(),
        default_locale=Locale("en"),
    )
    await notifier.notify(
        BossFightFinished(
            boss_fight=_boss_fight(status=BossFightStatus.FINISHED),
            raiders_won=False,
            total_granted_cm=50,
            boss_revoked_cm=0,
            raiders_revoked_cm=50,
            scroll_drops=(),
            was_already_finished=False,
        )
    )
    chat_ids = sorted(c.chat_id for c in bot.calls)
    assert chat_ids == [1001, 2002, 3003, 4004]
    assert all("en:bosses-battle-finished-defeat" in c.text for c in bot.calls)


@pytest.mark.asyncio
async def test_fight_finish_summoner_eliminated_still_gets_message() -> None:
    """Саммонер выбит из `participants`, но всё равно получает финальное."""
    bot = _FakeBot()
    # Саммонер id=1 НЕ в participants.
    participants = FakeBossParticipantRepository(
        rows=[
            _raider(player_id=3, boss_fight_id=99),
            _raider(player_id=4, boss_fight_id=99),
        ],
    )
    notifier = _make_fight_finish_notifier(
        bot=bot,
        participants=participants,
        bundle=FakeMessageBundle(),
        default_locale=Locale("en"),
    )
    await notifier.notify(
        BossFightFinished(
            boss_fight=_boss_fight(status=BossFightStatus.FINISHED),
            raiders_won=True,
            total_granted_cm=100,
            boss_revoked_cm=100,
            raiders_revoked_cm=0,
            scroll_drops=(),
            was_already_finished=False,
        )
    )
    chat_ids = sorted(c.chat_id for c in bot.calls)
    # Саммонер 1001 должен получить отдельный send.
    assert chat_ids == [1001, 2002, 3003, 4004]


@pytest.mark.asyncio
async def test_fight_finish_skips_when_summoner_player_missing() -> None:
    bot = _FakeBot()
    players = FakePlayerRepository(
        rows=[
            _player(player_id=2, tg_id=2002, length_cm=80),
            _player(player_id=3, tg_id=3003),
            _player(player_id=4, tg_id=4004),
        ]
    )
    notifier = _make_fight_finish_notifier(bot=bot, players=players)
    await notifier.notify(
        BossFightFinished(
            boss_fight=_boss_fight(status=BossFightStatus.FINISHED),
            raiders_won=True,
            total_granted_cm=100,
            boss_revoked_cm=100,
            raiders_revoked_cm=0,
            scroll_drops=(),
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_fight_finish_skips_when_boss_player_missing() -> None:
    bot = _FakeBot()
    players = FakePlayerRepository(
        rows=[
            _player(player_id=1, tg_id=1001, length_cm=30),
            _player(player_id=3, tg_id=3003),
            _player(player_id=4, tg_id=4004),
        ]
    )
    notifier = _make_fight_finish_notifier(bot=bot, players=players)
    await notifier.notify(
        BossFightFinished(
            boss_fight=_boss_fight(status=BossFightStatus.FINISHED),
            raiders_won=False,
            total_granted_cm=50,
            boss_revoked_cm=0,
            raiders_revoked_cm=50,
            scroll_drops=(),
            was_already_finished=False,
        )
    )
    assert bot.calls == []


@pytest.mark.asyncio
async def test_fight_finish_continues_when_participants_repo_fails() -> None:
    """Если participants-репо падает, рассылка по рейдерам пропускается,
    но боссу + саммонеру (если он не в participants) всё равно уходит."""
    bot = _FakeBot()

    class _BoomParticipants(FakeBossParticipantRepository):
        async def list_by_boss_fight(self, *, boss_fight_id: int) -> tuple[BossParticipant, ...]:
            raise RuntimeError("db down")

    notifier = _make_fight_finish_notifier(bot=bot, participants=_BoomParticipants())
    await notifier.notify(
        BossFightFinished(
            boss_fight=_boss_fight(status=BossFightStatus.FINISHED),
            raiders_won=True,
            total_granted_cm=100,
            boss_revoked_cm=100,
            raiders_revoked_cm=0,
            scroll_drops=(),
            was_already_finished=False,
        )
    )
    chat_ids = sorted(c.chat_id for c in bot.calls)
    # participants пуст → саммонер «не в participants» → отдельный send +
    # отдельный send боссу.
    assert chat_ids == [1001, 2002]


@pytest.mark.asyncio
async def test_fight_finish_swallows_telegram_api_error() -> None:
    bot = _FakeBot(raise_exc=_telegram_api_error())
    notifier = _make_fight_finish_notifier(bot=bot)
    await notifier.notify(
        BossFightFinished(
            boss_fight=_boss_fight(status=BossFightStatus.FINISHED),
            raiders_won=True,
            total_granted_cm=100,
            boss_revoked_cm=100,
            raiders_revoked_cm=0,
            scroll_drops=(),
            was_already_finished=False,
        )
    )
    # 3 рейдера + босс (саммонер уже в participants — отдельно не идёт).
    assert len(bot.calls) == 4


@pytest.mark.asyncio
async def test_fight_finish_swallows_unexpected_error() -> None:
    bot = _FakeBot(raise_exc=RuntimeError("network down"))
    notifier = _make_fight_finish_notifier(bot=bot)
    await notifier.notify(
        BossFightFinished(
            boss_fight=_boss_fight(status=BossFightStatus.FINISHED),
            raiders_won=False,
            total_granted_cm=50,
            boss_revoked_cm=0,
            raiders_revoked_cm=50,
            scroll_drops=(),
            was_already_finished=False,
        )
    )
    assert len(bot.calls) == 4


@pytest.mark.asyncio
async def test_fight_finish_renders_in_player_locale_ru() -> None:
    bot = _FakeBot()
    resolver = FakePlayerLocaleResolver()
    resolver.set_override(2002, Locale("ru"))
    notifier = _make_fight_finish_notifier(
        bot=bot,
        bundle=FakeMessageBundle(),
        locale_resolver=resolver,
        default_locale=Locale("en"),
    )
    await notifier.notify(
        BossFightFinished(
            boss_fight=_boss_fight(status=BossFightStatus.FINISHED),
            raiders_won=True,
            total_granted_cm=100,
            boss_revoked_cm=100,
            raiders_revoked_cm=0,
            scroll_drops=(),
            was_already_finished=False,
        )
    )
    by_chat = {c.chat_id: c.text for c in bot.calls}
    assert "ru:bosses-battle-finished-victory" in by_chat[2002]
    assert "en:bosses-battle-finished-victory" in by_chat[1001]
    assert "en:bosses-battle-finished-victory" in by_chat[3003]
    assert "en:bosses-battle-finished-victory" in by_chat[4004]


# --------------------------- locale-resolver edge cases ---------------------------


@pytest.mark.asyncio
async def test_locale_resolver_swallows_errors_and_falls_back_default() -> None:
    """Если резолвер локали упал — фолбэк на default_locale, ничего не падает."""
    bot = _FakeBot()

    @dataclass
    class _BoomResolver:
        async def resolve_for_tg_id(self, tg_id: int) -> Locale | None:
            raise RuntimeError("db down")

    notifier = _make_lobby_close_notifier(
        bot=bot,
        bundle=FakeMessageBundle(),
        locale_resolver=cast(IPlayerLocaleResolver, _BoomResolver()),
        default_locale=Locale("en"),
    )
    await notifier.notify(BossLobbyClosed(boss_fight=_boss_fight(), was_already_closed=False))
    assert all("en:bosses-battle-started" in c.text for c in bot.calls)
    assert len(bot.calls) == 3


@pytest.mark.asyncio
async def test_lobby_close_uses_default_logger_when_none_provided() -> None:
    bot = _FakeBot()
    # Без logger=... → используется внутренний `_LOGGER` модуля.
    notifier = _make_lobby_close_notifier(bot=bot, logger=None)
    await notifier.notify(BossLobbyClosed(boss_fight=_boss_fight(), was_already_closed=False))
    assert len(bot.calls) == 3
