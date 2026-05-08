"""Handler команды `/boss` (Спринт 3.3-D, ГДД §10).

Команда `/boss` (личка-only, без аргументов):

1. Принимаем команду только в личке. В группах — тихо игнорируем
   (UX-выбор: рейд глобальный, призыв логически — это «приватная»
   акция саммонера, и мы не хотим лишнего спама в групповых чатах).
2. Если в команде есть лишние аргументы — отдаём подсказку
   (`bosses-usage`).
3. Зовём `SummonBoss` use-case (он сам проверит регистрацию,
   заморозку, толщину/длину, кулдаун, активный лок, выберет босса
   случайно из топ-N по длине). На любую доменную ошибку — точечный
   локализованный ответ.
4. На успех — два сообщения в той же личке:
   - подтверждение саммонеру (`bosses-summoned-private`);
   - объявление с инлайн-кнопкой «Показать лобби»
     (`bosses-summoned-announcement` + `announcement_keyboard`).
   Объявление формирует «приглашение к рейду», которое саммонер
   может переслать в любой чат — клик «Показать лобби» в любом
   чате откроет полный lobby-UI с кнопками `join/leave/cancel`.

Callback-роутер `boss:` (Спринт 3.3-D, D.4):

- `boss:show_lobby:<id>` — read-only, рендерит карточку лобби
  (`lobby_state_text`) с кнопками `join/leave/cancel` и редактирует
  сообщение, под которым нажали.
- `boss:join:<id>` — `JoinBossLobby` use-case. На успех — toast +
  refresh lobby UI.
- `boss:leave:<id>` — для саммонера toast «отмени через cancel»;
  для рейдеров `LeaveBossLobby` use-case с маппингом ошибок и
  refresh lobby UI.
- `boss:cancel:<id>` — `CancelBossFight` use-case (только саммонер).
  На успех — toast + замена сообщения текстом «рейд отменён»
  (`cancel_message_text`) + снятие клавиатуры.

Все локали — через `BossPresenter` + `IMessageBundle`. Префикс
ключей `bosses-*` (множественное — исторический выбор файла локалей).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Final

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.bosses import (
    CancelBossFight,
    JoinBossLobby,
    LeaveBossLobby,
    SummonBoss,
)
from pipirik_wars.application.dto.inputs import (
    CancelBossFightInput,
    JoinBossLobbyInput,
    LeaveBossLobbyInput,
    SummonBossInput,
)
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import BossPresenter
from pipirik_wars.bot.presenters.bosses import parse_boss_callback_data
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.bosses import (
    AlreadyInBossFightError,
    BossFightLobbyClosedError,
    BossFightNotFoundError,
    BossFightRequirementError,
    BossPlayerPoolEmptyError,
    BossSummonOnGlobalCooldownError,
    IBossFightRepository,
    IBossParticipantRepository,
    InvalidBossFightStateError,
    NotAuthorizedToCancelBossError,
    NotInBossFightError,
)
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.player.errors import (
    PlayerFrozenError,
    PlayerNotFoundError,
)
from pipirik_wars.domain.shared.ports import IClock

router = Router(name="boss")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

_EXPECTED_ARG_COUNT: Final[int] = 0


@router.message(Command("boss"))
async def handle_boss(
    message: Message,
    tg_identity: TgIdentity | None,
    summon_boss: SummonBoss,
    get_profile: GetProfile,
    players: IPlayerRepository,
    balance: IBalanceConfig,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Команда `/boss` — призвать рейд-босса (личка-only, без аргументов)."""
    presenter = BossPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    # Не-личка — тихо игнорируем (см. модульный docstring). Это сознательный
    # UX-выбор: рейд глобальный, призыв — приватная акция саммонера.
    if chat_kind != "private" or tg_identity is None:
        return

    # Парсинг хвоста: `/boss` без аргументов; любой лишний — usage.
    if not _is_args_empty(message.text):
        cfg = balance.get().bosses
        await message.answer(
            presenter.usage(top_n_pool=cfg.top_n_pool, locale=effective_locale),
        )
        return

    try:
        result = await summon_boss.execute(
            SummonBossInput(summoner_tg_id=tg_identity.tg_user_id),
        )
    except (
        PlayerNotFoundError,
        PlayerFrozenError,
        BossFightRequirementError,
        BossSummonOnGlobalCooldownError,
        AlreadyInBossFightError,
        BossPlayerPoolEmptyError,
    ) as exc:
        await _answer_summon_boss_error(
            message=message,
            exc=exc,
            presenter=presenter,
            locale=effective_locale,
        )
        return

    cfg = balance.get().bosses
    boss_fight = result.boss_fight
    assert boss_fight.id is not None

    summoner_view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if summoner_view is None:  # pragma: no cover — игрок только что прошёл use-case
        _LOGGER.warning(
            "boss: summoner profile not found right after SummonBoss",
            extra={"tg_id": tg_identity.tg_user_id, "boss_fight_id": boss_fight.id},
        )
        return
    boss_view = await _profile_by_player_id(
        player_id=boss_fight.boss_player_id,
        players=players,
        get_profile=get_profile,
    )
    if boss_view is None:  # pragma: no cover — босс только что был выбран use-case-ом
        _LOGGER.error(
            "boss: boss profile vanished right after SummonBoss",
            extra={"boss_fight_id": boss_fight.id, "boss_player_id": boss_fight.boss_player_id},
        )
        return

    await message.answer(
        presenter.summoned_private(
            boss=boss_view.player,
            boss_display_name=boss_view.display_name,
            boss_length_cm=boss_fight.current_boss_length_cm,
            lobby_minutes=cfg.lobby_minutes,
            locale=effective_locale,
        ),
    )

    announcement_text = presenter.summoned_announcement(
        summoner=summoner_view.player,
        summoner_display_name=summoner_view.display_name,
        boss=boss_view.player,
        boss_display_name=boss_view.display_name,
        boss_length_cm=boss_fight.current_boss_length_cm,
        lobby_minutes=cfg.lobby_minutes,
        locale=effective_locale,
    )
    keyboard = presenter.announcement_keyboard(
        boss_fight_id=boss_fight.id,
        locale=effective_locale,
    )
    try:
        await message.answer(text=announcement_text, reply_markup=keyboard)
    except TelegramAPIError as exc:  # pragma: no cover — Telegram-ошибка post-фактум
        _LOGGER.warning(
            "boss: failed to post announcement message",
            extra={
                "boss_fight_id": boss_fight.id,
                "tg_id": tg_identity.tg_user_id,
                "error": str(exc),
            },
        )


def _is_args_empty(text: str | None) -> bool:
    """Проверить, что у `/boss` нет лишних аргументов.

    Telegram кладёт в `message.text` всю команду целиком (включая
    `/boss` или `/boss@bot_username`). «Пусто» — это либо `None`, либо
    одна часть после `split()`.
    """
    if not text:
        return True
    parts = text.strip().split()
    return len(parts) == _EXPECTED_ARG_COUNT + 1


async def _answer_summon_boss_error(  # noqa: PLR0911 — единая точка маппинга доменных ошибок use-case в локали
    *,
    message: Message,
    exc: Exception,
    presenter: BossPresenter,
    locale: Locale,
) -> None:
    """Маппинг доменных ошибок `SummonBoss` в локализованные ответы."""
    if isinstance(exc, PlayerNotFoundError):
        await message.answer(presenter.not_registered(locale=locale))
        return
    if isinstance(exc, PlayerFrozenError):
        await message.answer(presenter.player_frozen(locale=locale))
        return
    if isinstance(exc, BossFightRequirementError):
        if exc.requirement == "thickness":
            await message.answer(
                presenter.requirement_thickness(
                    required=exc.required,
                    actual=exc.actual,
                    locale=locale,
                ),
            )
            return
        await message.answer(
            presenter.requirement_length(
                required_cm=exc.required,
                actual_cm=exc.actual,
                locale=locale,
            ),
        )
        return
    if isinstance(exc, BossSummonOnGlobalCooldownError):
        await message.answer(
            presenter.cooldown(
                remaining_seconds=exc.actual_remaining_seconds,
                locale=locale,
            ),
        )
        return
    if isinstance(exc, AlreadyInBossFightError):
        await message.answer(presenter.already_in(locale=locale))
        return
    if isinstance(exc, BossPlayerPoolEmptyError):
        await message.answer(presenter.pool_empty(locale=locale))
        return
    raise exc  # pragma: no cover — все ветки покрыты except-блоком в handler-е


@router.callback_query(F.data.startswith("boss:"))
async def handle_boss_callback(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    join_boss_lobby: JoinBossLobby,
    leave_boss_lobby: LeaveBossLobby,
    cancel_boss_fight: CancelBossFight,
    boss_fights: IBossFightRepository,
    boss_participants: IBossParticipantRepository,
    players: IPlayerRepository,
    get_profile: GetProfile,
    clock: IClock,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Маршрутизатор инлайн-кнопок рейд-босса (D.4).

    Поддержанные `action`-ы:

    - `show_lobby` — открыть карточку лобби (read-side: грузит
      `BossFight` + участников + саммонера + босса; рендерит
      `lobby_state_text` с клавиатурой `join/leave/cancel`).
    - `join` — `JoinBossLobby` use-case; на успех — toast + refresh
      lobby UI.
    - `leave` — для саммонера toast «нужен cancel»; для рейдеров
      `LeaveBossLobby` use-case + refresh lobby UI.
    - `cancel` — `CancelBossFight` use-case (use-case сам проверит
      авторизацию). На успех — toast + замена сообщения «рейд отменён»
      + снятие клавиатуры.
    """
    if tg_identity is None or callback.data is None or callback.message is None:
        return

    presenter = BossPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parsed = parse_boss_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "boss.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(
            presenter.callback_toast_generic_error(locale=effective_locale),
            show_alert=False,
        )
        return

    if parsed.action == "show_lobby":
        await _handle_show_lobby_callback(
            callback=callback,
            boss_fight_id=parsed.boss_fight_id,
            boss_fights=boss_fights,
            boss_participants=boss_participants,
            players=players,
            get_profile=get_profile,
            clock=clock,
            presenter=presenter,
            locale=effective_locale,
        )
        return

    if parsed.action == "join":
        await _handle_join_callback(
            callback=callback,
            tg_identity=tg_identity,
            boss_fight_id=parsed.boss_fight_id,
            join_boss_lobby=join_boss_lobby,
            boss_fights=boss_fights,
            boss_participants=boss_participants,
            players=players,
            get_profile=get_profile,
            clock=clock,
            presenter=presenter,
            locale=effective_locale,
        )
        return

    if parsed.action == "leave":
        await _handle_leave_callback(
            callback=callback,
            tg_identity=tg_identity,
            boss_fight_id=parsed.boss_fight_id,
            leave_boss_lobby=leave_boss_lobby,
            boss_fights=boss_fights,
            boss_participants=boss_participants,
            players=players,
            get_profile=get_profile,
            clock=clock,
            presenter=presenter,
            locale=effective_locale,
        )
        return

    if parsed.action == "cancel":
        await _handle_cancel_callback(
            callback=callback,
            tg_identity=tg_identity,
            boss_fight_id=parsed.boss_fight_id,
            cancel_boss_fight=cancel_boss_fight,
            presenter=presenter,
            locale=effective_locale,
        )
        return

    # Все четыре action-а уже обработаны выше; защитный ack — на случай
    # рассинхронизации `_VALID_ACTIONS` в presenter и dispatch-цепочки.
    await callback.answer()  # pragma: no cover — все ветки покрыты выше


async def _handle_show_lobby_callback(
    *,
    callback: CallbackQuery,
    boss_fight_id: int,
    boss_fights: IBossFightRepository,
    boss_participants: IBossParticipantRepository,
    players: IPlayerRepository,
    get_profile: GetProfile,
    clock: IClock,
    presenter: BossPresenter,
    locale: Locale,
) -> None:
    """Логика callback-а «Показать лобби» (`boss:show_lobby:<id>`).

    Read-only: грузит рейд-бой + участников + саммонера + босса,
    рендерит актуальный текст лобби + клавиатуру с join/leave/cancel,
    редактирует сообщение в чате (best-effort).
    """
    boss_fight = await boss_fights.get_by_id(boss_fight_id=boss_fight_id)
    if boss_fight is None:
        await callback.answer(
            presenter.callback_toast_fight_not_found(locale=locale),
            show_alert=False,
        )
        return
    if not boss_fight.is_in_lobby:
        await callback.answer(
            presenter.callback_toast_invalid_state(locale=locale),
            show_alert=False,
        )
        return

    summoner_view = await _profile_by_player_id(
        player_id=boss_fight.summoner_player_id,
        players=players,
        get_profile=get_profile,
    )
    if summoner_view is None:  # pragma: no cover — битая FK, защитный путь
        _LOGGER.error(
            "boss.show_lobby: summoner profile not found",
            extra={
                "boss_fight_id": boss_fight_id,
                "summoner_player_id": boss_fight.summoner_player_id,
            },
        )
        await callback.answer(
            presenter.callback_toast_generic_error(locale=locale),
            show_alert=False,
        )
        return
    boss_view = await _profile_by_player_id(
        player_id=boss_fight.boss_player_id,
        players=players,
        get_profile=get_profile,
    )
    if boss_view is None:  # pragma: no cover — битая FK
        _LOGGER.error(
            "boss.show_lobby: boss profile not found",
            extra={
                "boss_fight_id": boss_fight_id,
                "boss_player_id": boss_fight.boss_player_id,
            },
        )
        await callback.answer(
            presenter.callback_toast_generic_error(locale=locale),
            show_alert=False,
        )
        return

    participants = await boss_participants.list_by_boss_fight(boss_fight_id=boss_fight_id)
    now = clock.now()

    text = presenter.lobby_state_text(
        boss_fight=boss_fight,
        raiders_count=len(participants),
        summoner=summoner_view.player,
        summoner_display_name=summoner_view.display_name,
        boss=boss_view.player,
        boss_display_name=boss_view.display_name,
        now=now,
        locale=locale,
    )
    keyboard = presenter.lobby_keyboard(boss_fight_id=boss_fight_id, locale=locale)

    await callback.answer()
    msg = callback.message
    if msg is None:
        return
    with contextlib.suppress(Exception):
        await msg.edit_text(text=text, reply_markup=keyboard)  # type: ignore[union-attr]


async def _handle_join_callback(
    *,
    callback: CallbackQuery,
    tg_identity: TgIdentity,
    boss_fight_id: int,
    join_boss_lobby: JoinBossLobby,
    boss_fights: IBossFightRepository,
    boss_participants: IBossParticipantRepository,
    players: IPlayerRepository,
    get_profile: GetProfile,
    clock: IClock,
    presenter: BossPresenter,
    locale: Locale,
) -> None:
    """Логика callback-а «Вступить в рейд» (`boss:join:<id>`, D.4).

    Зовёт `JoinBossLobby` use-case (он сам проверит лобби-статус,
    толщину/длину, не-боссость, не-двойной вход). На каждый доменный
    отказ — локализованный toast. На успех — toast + refresh lobby UI.

    Различение «уже босс» vs «уже участник» по `AlreadyInBossFightError`:
    use-case бросает один тип ошибки в обоих случаях; читаем `boss_fight`
    отдельно и сверяемся с `boss_player_id`, чтобы дать точечный toast.
    """
    try:
        await join_boss_lobby.execute(
            JoinBossLobbyInput(
                tg_id=tg_identity.tg_user_id,
                boss_fight_id=boss_fight_id,
            ),
        )
    except BossFightNotFoundError:
        await callback.answer(
            presenter.callback_toast_fight_not_found(locale=locale),
            show_alert=False,
        )
        return
    except BossFightLobbyClosedError:
        await callback.answer(
            presenter.callback_toast_lobby_closed(locale=locale),
            show_alert=False,
        )
        return
    except PlayerNotFoundError:
        await callback.answer(
            presenter.callback_toast_player_not_found(locale=locale),
            show_alert=False,
        )
        return
    except PlayerFrozenError:
        await callback.answer(
            presenter.callback_toast_player_frozen(locale=locale),
            show_alert=False,
        )
        return
    except AlreadyInBossFightError:
        # Различаем «ты сам босс» vs «уже участник»: use-case бросает
        # единый тип, а UX-сообщения разные.
        toast = await _resolve_already_in_toast(
            tg_identity=tg_identity,
            boss_fight_id=boss_fight_id,
            boss_fights=boss_fights,
            get_profile=get_profile,
            presenter=presenter,
            locale=locale,
        )
        await callback.answer(toast, show_alert=False)
        return
    except BossFightRequirementError as exc:
        if exc.requirement == "thickness":
            text = presenter.callback_toast_requirement_thickness(
                required=exc.required,
                actual=exc.actual,
                locale=locale,
            )
        else:
            text = presenter.callback_toast_requirement_length(
                required_cm=exc.required,
                actual_cm=exc.actual,
                locale=locale,
            )
        await callback.answer(text, show_alert=False)
        return

    await callback.answer(
        presenter.join_toast_success(locale=locale),
        show_alert=False,
    )
    await _refresh_lobby_message(
        callback=callback,
        boss_fight_id=boss_fight_id,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        players=players,
        get_profile=get_profile,
        clock=clock,
        presenter=presenter,
        locale=locale,
    )


async def _resolve_already_in_toast(
    *,
    tg_identity: TgIdentity,
    boss_fight_id: int,
    boss_fights: IBossFightRepository,
    get_profile: GetProfile,
    presenter: BossPresenter,
    locale: Locale,
) -> str:
    """Подобрать корректный toast при `AlreadyInBossFightError` на join.

    Use-case `JoinBossLobby` бросает одну ошибку в двух кейсах:
    игрок — сам босс этого рейда (`_ensure_not_boss`), и игрок —
    уже участник (`_ensure_not_yet_participant` либо лок). Различаем
    через `boss_fight.boss_player_id == player.id`. На любые
    «отвалилось чтение» — fallback на «уже участник».
    """
    boss_fight = await boss_fights.get_by_id(boss_fight_id=boss_fight_id)
    if boss_fight is None:  # pragma: no cover — race с cancel-ом use-case-а
        return presenter.callback_toast_already_in_fight(locale=locale)
    summoner_view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if summoner_view is None:  # pragma: no cover — игрок только что прошёл use-case
        return presenter.callback_toast_already_in_fight(locale=locale)
    if summoner_view.player.id is not None and summoner_view.player.id == boss_fight.boss_player_id:
        return presenter.callback_toast_cannot_join_as_boss(locale=locale)
    return presenter.callback_toast_already_in_fight(locale=locale)


async def _handle_leave_callback(  # noqa: PLR0911 — единая точка маппинга доменных ошибок use-case в локали
    *,
    callback: CallbackQuery,
    tg_identity: TgIdentity,
    boss_fight_id: int,
    leave_boss_lobby: LeaveBossLobby,
    boss_fights: IBossFightRepository,
    boss_participants: IBossParticipantRepository,
    players: IPlayerRepository,
    get_profile: GetProfile,
    clock: IClock,
    presenter: BossPresenter,
    locale: Locale,
) -> None:
    """Логика callback-а «Покинуть» (`boss:leave:<id>`, D.4).

    Особый кейс: саммонер технически может выйти через `LeaveBossLobby`,
    но в UI-флоу мы предпочитаем явный «Отменить рейд». Поэтому
    pre-check: если игрок — саммонер этого рейда, отдаём toast
    «нажми Отменить рейд» и НЕ зовём use-case (бой остаётся в `LOBBY`,
    локи не трогаются — саммонер сам решит, отменять или нет).

    Для не-саммонера зовём `LeaveBossLobby` use-case с маппингом
    доменных ошибок (`BossFightNotFoundError`, `BossFightLobbyClosedError`,
    `PlayerNotFoundError`, `NotInBossFightError`).
    """
    boss_fight = await boss_fights.get_by_id(boss_fight_id=boss_fight_id)
    if boss_fight is None:
        await callback.answer(
            presenter.callback_toast_fight_not_found(locale=locale),
            show_alert=False,
        )
        return
    if not boss_fight.is_in_lobby:
        await callback.answer(
            presenter.callback_toast_lobby_closed(locale=locale),
            show_alert=False,
        )
        return

    player_view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if player_view is None:
        await callback.answer(
            presenter.callback_toast_player_not_found(locale=locale),
            show_alert=False,
        )
        return
    if player_view.player.id is not None and player_view.player.id == boss_fight.summoner_player_id:
        await callback.answer(
            presenter.leave_toast_summoner_leaves(locale=locale),
            show_alert=False,
        )
        return

    try:
        await leave_boss_lobby.execute(
            LeaveBossLobbyInput(
                tg_id=tg_identity.tg_user_id,
                boss_fight_id=boss_fight_id,
            ),
        )
    except BossFightNotFoundError:
        await callback.answer(
            presenter.callback_toast_fight_not_found(locale=locale),
            show_alert=False,
        )
        return
    except BossFightLobbyClosedError:
        await callback.answer(
            presenter.callback_toast_lobby_closed(locale=locale),
            show_alert=False,
        )
        return
    except PlayerNotFoundError:
        await callback.answer(
            presenter.callback_toast_player_not_found(locale=locale),
            show_alert=False,
        )
        return
    except NotInBossFightError:
        await callback.answer(
            presenter.leave_toast_not_a_participant(locale=locale),
            show_alert=False,
        )
        return

    await callback.answer(
        presenter.leave_toast_success(locale=locale),
        show_alert=False,
    )
    await _refresh_lobby_message(
        callback=callback,
        boss_fight_id=boss_fight_id,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        players=players,
        get_profile=get_profile,
        clock=clock,
        presenter=presenter,
        locale=locale,
    )


async def _handle_cancel_callback(
    *,
    callback: CallbackQuery,
    tg_identity: TgIdentity,
    boss_fight_id: int,
    cancel_boss_fight: CancelBossFight,
    presenter: BossPresenter,
    locale: Locale,
) -> None:
    """Логика callback-а отмены рейда (`boss:cancel:<id>`, D.4).

    Зовёт `CancelBossFight` use-case (он сам проверит саммонерство и
    статус). На каждый доменный отказ — локализованный toast. На успех
    (или идемпотентный no-op) — toast + замена сообщения текстом
    «рейд отменён» + снятие клавиатуры.
    """
    try:
        result = await cancel_boss_fight.execute(
            CancelBossFightInput(
                boss_fight_id=boss_fight_id,
                tg_id=tg_identity.tg_user_id,
            ),
        )
    except BossFightNotFoundError:
        await callback.answer(
            presenter.callback_toast_fight_not_found(locale=locale),
            show_alert=False,
        )
        return
    except InvalidBossFightStateError:
        await callback.answer(
            presenter.callback_toast_invalid_state(locale=locale),
            show_alert=False,
        )
        return
    except NotAuthorizedToCancelBossError:
        await callback.answer(
            presenter.callback_toast_not_summoner(locale=locale),
            show_alert=False,
        )
        return
    except PlayerNotFoundError:
        await callback.answer(
            presenter.callback_toast_player_not_found(locale=locale),
            show_alert=False,
        )
        return

    if result.was_already_cancelled:
        await callback.answer(
            presenter.cancel_toast_already_cancelled(locale=locale),
            show_alert=False,
        )
    else:
        await callback.answer(
            presenter.cancel_toast_success(locale=locale),
            show_alert=False,
        )

    await _replace_with_cancelled(
        callback=callback,
        text=presenter.cancel_message_text(locale=locale),
    )


async def _refresh_lobby_message(
    *,
    callback: CallbackQuery,
    boss_fight_id: int,
    boss_fights: IBossFightRepository,
    boss_participants: IBossParticipantRepository,
    players: IPlayerRepository,
    get_profile: GetProfile,
    clock: IClock,
    presenter: BossPresenter,
    locale: Locale,
) -> None:
    """Перерендерить lobby-сообщение после mut-callback-а (join/leave).

    Best-effort: если что-то пошло не так на read-side (битая FK,
    рейд внезапно закрылся между join-ом и refresh-ем) — молчим,
    use-case уже отработал, toast пользователю отдан.
    """
    boss_fight = await boss_fights.get_by_id(boss_fight_id=boss_fight_id)
    if boss_fight is None or not boss_fight.is_in_lobby:
        return

    summoner_view = await _profile_by_player_id(
        player_id=boss_fight.summoner_player_id,
        players=players,
        get_profile=get_profile,
    )
    if summoner_view is None:  # pragma: no cover — битая FK
        return
    boss_view = await _profile_by_player_id(
        player_id=boss_fight.boss_player_id,
        players=players,
        get_profile=get_profile,
    )
    if boss_view is None:  # pragma: no cover — битая FK
        return

    participants = await boss_participants.list_by_boss_fight(boss_fight_id=boss_fight_id)
    now = clock.now()

    text = presenter.lobby_state_text(
        boss_fight=boss_fight,
        raiders_count=len(participants),
        summoner=summoner_view.player,
        summoner_display_name=summoner_view.display_name,
        boss=boss_view.player,
        boss_display_name=boss_view.display_name,
        now=now,
        locale=locale,
    )
    keyboard = presenter.lobby_keyboard(boss_fight_id=boss_fight_id, locale=locale)
    msg = callback.message
    if msg is None:
        return
    with contextlib.suppress(Exception):
        await msg.edit_text(text=text, reply_markup=keyboard)  # type: ignore[union-attr]


async def _profile_by_player_id(
    *,
    player_id: int,
    players: IPlayerRepository,
    get_profile: GetProfile,
) -> ProfileView | None:
    """Получить `ProfileView` по доменному `player_id`.

    `GetProfile.execute(tg_id=...)` принимает только tg_id, поэтому
    сначала достаём `Player` из репо по id, затем через `tg_id` —
    `ProfileView` (нужен `display_name` и `Player` с актуальным
    балансом-зависимым названием).
    """
    player = await players.get_by_id(player_id=player_id)
    if player is None:
        return None
    return await get_profile.execute(tg_id=player.tg_id)


async def _replace_with_cancelled(
    *,
    callback: CallbackQuery,
    text: str,
) -> None:
    """Заменить текст сообщения на «рейд отменён» и снять клавиатуру.

    Best-effort: если Telegram не даст отредактировать (сообщение
    слишком старое, etc.) — молчим, use-case уже отработал, аудит
    записан, токен callback-а потрачен.
    """
    msg = callback.message
    if msg is None:
        return
    with contextlib.suppress(Exception):
        await msg.edit_text(text=text)  # type: ignore[union-attr]
