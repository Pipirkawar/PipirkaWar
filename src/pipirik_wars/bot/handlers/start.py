"""`/start` handler (Спринт 1.1.C → 1.1.D → 1.2.4 DAU Gate → 1.5.B i18n
→ 2.4.D реферальная система).

Acceptance criteria из `development_plan.md`:
- Спринт 1.1.1: `/start` отвечает в ЛС, в группе и в супергруппе.
- Спринт 1.1.3: регистрация игрока **только через ЛС** (`chat_type == "private"`).
- Спринт 1.2.4: при `DAU >= MAX_DAU` показываем «серверы переполнены,
  позиция #N».
- Спринт 1.5.B: все ответы — через `StartPresenter`/`IMessageBundle`,
  никаких hardcoded-строк в handler-е.
- Спринт 2.4.D / 2.4.1: парсинг `start=ref_<id>` payload-а в ЛС, привязка
  реферальной связи и начисление signup-бонуса (+5 см новичку, +1 см
  рефереру). В группе/супергруппе payload игнорируется (игроки не
  регистрируются в чатах кланов).

В ЛС handler вызывает `RegisterPlayer` (с `locale = data["locale"].code`,
полученным из `LocaleMiddleware` — ПД 1.5.2). В группе/супергруппе —
выводит инструкцию (бот сам не регистрирует игрока в группе, чтобы не
плодить случайных новичков из соседних чатов). В прочих типах
(`channel` и т.п.) шлём нейтральное сообщение.

Реферальный flow (только в ЛС):
- `command.args == "ref_<digits>"` → парсим `referrer_tg_id`. Любой
  кривой формат (буквы, отрицательные числа, ноль, переполнение) —
  тихо игнорируется (как будто рефки не было).
- Самореферал (`referrer_tg_id == own_tg_id`) — тихо игнорируется.
- После успешного `RegisterPlayer.execute(...)`:
  - `RegisterReferral` (создаёт запись в `referrals`); если запись уже
    есть (re-delivery `/start`) — `ReferralAlreadyRegistered` swallow-ится;
  - `GrantReferralSignupBonus` (начисляет +5 см новичку, +1 см
    рефереру); если бонус уже выдан — `SignupBonusAlreadyGrantedError`
    swallow-ится.
  - Любые `ReferrerNotRegisteredError` / `SelfReferralError` — silent
    no-op (игрок не должен видеть «реферер не найден» — это не его
    проблема, и это даёт антифрод-гэтт против скан-атаки).
- На `PlayerAlreadyRegisteredError` (повторный entry) — *не* пытаемся
  заново привязать рефку: первый успешный `/start` уже её обработал
  (или сознательно проигнорировал из-за самореферала / невалидного
  payload-а). Дополнительные попытки могут только породить
  «опоздавшие» рефки на свежезалогиненных игроков.

Все технические ошибки use-case-а ловит `ErrorHandlerMiddleware`;
handler ловит только три бизнес-кейса: уже зарегистрирован
(`PlayerAlreadyRegisteredError`), уже стоит в очереди (`AlreadyQueuedError`),
и discriminated union `RegisterPlayerResult` для развилки registered/queued.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from pipirik_wars.application.dto.inputs import (
    GrantReferralSignupBonusInput,
    RegisterPlayerInput,
    RegisterReferralInput,
)
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.player import (
    PlayerQueued,
    PlayerRegistered,
    RegisterPlayer,
)
from pipirik_wars.application.referral import (
    GrantReferralSignupBonus,
    RegisterReferral,
)
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.start import StartPresenter
from pipirik_wars.domain.player import PlayerAlreadyRegisteredError
from pipirik_wars.domain.referral import (
    ReferrerNotRegisteredError,
    SelfReferralError,
    SignupBonusAlreadyGrantedError,
)
from pipirik_wars.domain.signup_queue import (
    AlreadyQueuedError,
    ISignupQueueRepository,
)

logger = logging.getLogger(__name__)

router = Router(name="start")

_REF_PREFIX = "ref_"


@router.message(CommandStart(deep_link=False))
async def handle_start(
    message: Message,
    tg_identity: TgIdentity | None,
    register_player: RegisterPlayer,
    register_referral: RegisterReferral,
    grant_referral_signup_bonus: GrantReferralSignupBonus,
    signup_queue: ISignupQueueRepository,
    bundle: IMessageBundle,
    command: CommandObject | None = None,
    locale: Locale | None = None,
) -> None:
    """Отвечает на `/start`.

    В ЛС — регистрирует игрока ИЛИ ставит в очередь (DAU Gate);
    в группе/супергруппе — отдаёт инструкцию; в прочих типах — нейтрально.

    `tg_identity`, use-case-ы, `signup_queue` и `bundle` приходят
    через aiogram workflow-data DI. `locale` приходит из
    `LocaleMiddleware` (там же ключ `data["locale"]`); `None` означает,
    что middleware не сработал (в тестах допустимо) — берём fallback EN.
    `command` — тоже опциональный; если передан, `command.args` хранит
    payload `start=...` (для парсинга `ref_<id>`).
    """
    presenter = StartPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind == "private":
        if tg_identity is None:
            await message.answer(presenter.other(locale=effective_locale))
            return
        referrer_tg_id = _parse_referrer(
            payload=command.args if command is not None else None,
            own_tg_id=tg_identity.tg_user_id,
        )
        try:
            result = await register_player.execute(
                RegisterPlayerInput(
                    tg_id=tg_identity.tg_user_id,
                    username=_username_of(message),
                    locale=effective_locale.code,
                    referrer_tg_id=referrer_tg_id,
                )
            )
        except PlayerAlreadyRegisteredError:
            await message.answer(presenter.already(locale=effective_locale))
            return
        except AlreadyQueuedError:
            existing = await signup_queue.get_by_tg_id(tg_identity.tg_user_id)
            position = existing.position if existing is not None else 0
            await message.answer(
                presenter.queued(locale=effective_locale, position=position),
            )
            return
        if isinstance(result, PlayerRegistered):
            bonus_cm = await _try_apply_referral(
                register_referral=register_referral,
                grant_referral_signup_bonus=grant_referral_signup_bonus,
                referrer_tg_id=referrer_tg_id,
                referred_tg_id=tg_identity.tg_user_id,
            )
            if bonus_cm > 0:
                await message.answer(
                    presenter.registered_with_referral(
                        locale=effective_locale,
                        bonus_cm=bonus_cm,
                    ),
                )
            else:
                await message.answer(presenter.registered(locale=effective_locale))
        elif isinstance(result, PlayerQueued):
            await message.answer(
                presenter.queued(
                    locale=effective_locale,
                    position=result.entry.position,
                ),
            )
        return

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return

    await message.answer(presenter.other(locale=effective_locale))


def _parse_referrer(*, payload: str | None, own_tg_id: int) -> int | None:
    """Извлечь `referrer_tg_id` из payload-а `start=ref_<id>`.

    Возвращает `None` для всех «нерефовых» случаев:
    - payload не передан / пустой / не начинается с `ref_`;
    - суффикс не является целым положительным числом;
    - саморефералинг (`referrer == own`).
    """
    if payload is None or not payload.startswith(_REF_PREFIX):
        return None
    suffix = payload[len(_REF_PREFIX) :]
    if not suffix.isdigit():
        return None
    try:
        referrer_tg_id = int(suffix)
    except ValueError:
        return None
    if referrer_tg_id <= 0 or referrer_tg_id == own_tg_id:
        return None
    return referrer_tg_id


async def _try_apply_referral(
    *,
    register_referral: RegisterReferral,
    grant_referral_signup_bonus: GrantReferralSignupBonus,
    referrer_tg_id: int | None,
    referred_tg_id: int,
) -> int:
    """Привязать рефералку и начислить signup-бонус новичку.

    Возвращает `bonus_cm` (см, начисленные новичку), или `0` если
    рефералка не сработала (без рефки / реферер не зарегистрирован /
    бонус уже выдан / любая другая no-op-ситуация).

    Все доменные «бизнес-no-op-ы» (`SelfReferralError`,
    `ReferrerNotRegisteredError`, `SignupBonusAlreadyGrantedError`)
    swallow-ятся: для игрока «реферка просто не сработала», без
    видимой ошибки. Технические ошибки (DB и т.п.) пробрасываются —
    их ловит `ErrorHandlerMiddleware`.
    """
    if referrer_tg_id is None:
        return 0

    try:
        await register_referral.execute(
            RegisterReferralInput(
                referrer_tg_id=referrer_tg_id,
                referred_tg_id=referred_tg_id,
            )
        )
    except (ReferrerNotRegisteredError, SelfReferralError):
        # Реферер не зарегистрирован или ошибочный self-ref (DTO-валидатор
        # его обычно не пропустит, но у нас defense-in-depth). Тихо
        # пропускаем — пользователь даже не увидит, что рефка была.
        logger.info(
            "Referral skipped: referrer_tg_id=%s, referred_tg_id=%s",
            referrer_tg_id,
            referred_tg_id,
        )
        return 0

    try:
        granted = await grant_referral_signup_bonus.execute(
            GrantReferralSignupBonusInput(referred_tg_id=referred_tg_id)
        )
    except SignupBonusAlreadyGrantedError:
        # Re-delivery `/start ref_<id>` после того, как первый вызов уже
        # начислил бонус. Игрок видит обычное «уже зарегистрирован»
        # выше по стеку — сюда мы попадём только если он каким-то образом
        # снова прошёл `RegisterPlayer.execute(...)` (этого не должно
        # быть). Логируем, продолжаем без бонусной плашки.
        logger.warning(
            "Signup bonus already granted on second RegisterPlayer success: %s",
            referred_tg_id,
        )
        return 0
    return granted.newbie_bonus_cm


def _username_of(message: Message) -> str | None:
    """Достаёт `@username` отправителя без `@`. None, если username не задан."""
    if message.from_user is None:
        return None
    name = message.from_user.username
    return name if name else None
