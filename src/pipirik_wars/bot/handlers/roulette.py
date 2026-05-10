"""Handler команды `/roulette_free` (Спринт 3.5-D, ГДД §12.4).

`/roulette_free` (Free-to-play рулетка) в личке бота:

1. Зовёт `GetProfile` use-case — берёт текущего игрока, его длину и
   уровень толщины. Если игрок не найден — `not_registered`.
2. Считает pre-spin gate-ы по `RouletteFreeConfig` (с учётом hot-reload
   через `IBalanceConfig`):
   - `player.thickness.level >= roulette.free.min_thickness_level` (≥ 2);
   - `player.length.cm >= roulette.free.cost_cm` (≥ 100 см).
3. На любом из gate-фейлов отвечает `RoulettePresenter.requirement_*`
   карточкой и **не** показывает кнопку «Прокрутить» — это снимает
   риск дорогостоящей UoW-транзакции на заведомо проигрышной попытке.
4. На прохождении gate-ов отвечает `RoulettePresenter.prompt(...)` +
   кнопка `[Прокрутить — 100 см]` (callback_data `roulette_free:spin`).

В группе/супергруппе — короткая инструкция «открой ЛС» (как у `/upgrade`,
`/forest` и `/profile`).

Кнопка `[Прокрутить — 100 см]` (`roulette_free:spin`):

1. Идемпотентность handler-уровневая: ключ —
   `f"msg:{callback.message.message_id}"`. Тот же `callback.message`
   ⇒ тот же `idempotency_key` ⇒ use-case повторно не выполнит spin
   (вернёт `SpinResult(idempotent=True)`), даже если пользователь
   несколько раз нажал кнопку до её снятия.
2. Анимация — 3 кадра через `edit_text` с короткой паузой между ними
   (`_DEFAULT_FRAME_DELAY_S`). Длительность настраиваемая через
   keyword-аргумент `frame_delay_s` для unit-тестов.
3. Затем зовёт `SpinFreeRoulette.execute(...)`. Маппинг исходов:
   - `SpinResult(idempotent=True)` → `result_idempotent` карточка +
     toast `toast_already_processed`.
   - `SpinResult(outcome=..., idempotent=False)` → `render_result`
     карточка по `outcome.kind` (LENGTH с дельтой см / ITEM /
     SCROLL_REGULAR / SCROLL_BLESSED / CRYPTO_LOT) + toast
     `toast_spin_complete`.
4. Маппинг доменных ошибок:
   - `RouletteThicknessGateError` → toast + `requirement_thickness`
     карточка (use-case проверяет конфиг повторно, поэтому
     handler-pre-check всё равно может пропустить, если YAML был
     hot-reload-нут между показом prompt-а и нажатием).
   - `InsufficientLengthForRouletteError` → toast +
     `requirement_length` карточка (между показом и кликом игрок
     успел потратить длину в другой активности).
   - `PlayerNotFoundError` → `not_registered` (race с unregister-ом).
   - Любая другая ошибка — toast `toast_error`, клавиатура снимается;
     текст сообщения не правится, чтобы не затирать prompt с числами.

В отличие от `/upgrade`, у рулетки нет «Отмены»: чтобы выйти из
prompt-а — просто игнорируешь сообщение или закрываешь чат. Это
сознательное упрощение UX (1-кнопка-1-результат).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Final

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.player import GetProfile
from pipirik_wars.application.roulette import (
    SpinFreeRoulette,
    SpinFreeRouletteCommand,
)
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import (
    RoulettePresenter,
    parse_roulette_callback_data,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.roulette import (
    InsufficientLengthForRouletteError,
    RouletteThicknessGateError,
)

router = Router(name="roulette")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

# Длительность задержки между кадрами анимации (в секундах). Подобрана
# так, чтобы вся анимация занимала ~1.5 секунды — достаточно, чтобы
# пользователь увидел все 3 кадра, но не настолько долго, чтобы
# раздражать. В тестах значение переопределяется через keyword-аргумент.
_DEFAULT_FRAME_DELAY_S: Final[float] = 0.5


@router.message(Command("roulette_free"))
async def handle_roulette_free(
    message: Message,
    tg_identity: TgIdentity | None,
    get_profile: GetProfile,
    balance: IBalanceConfig,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Команда `/roulette_free` — показать pre-spin карточку с кнопкой."""
    presenter = RoulettePresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return

    player = view.player
    cfg = balance.get().roulette.free

    if player.thickness.level < cfg.min_thickness_level:
        await message.answer(
            presenter.requirement_thickness(
                required=cfg.min_thickness_level,
                actual=player.thickness.level,
                locale=effective_locale,
            )
        )
        return

    if player.length.cm < cfg.cost_cm:
        await message.answer(
            presenter.requirement_length(
                required_cm=cfg.cost_cm,
                actual_cm=player.length.cm,
                locale=effective_locale,
            )
        )
        return

    text = presenter.prompt(
        current_length_cm=player.length.cm,
        cost_cm=cfg.cost_cm,
        locale=effective_locale,
    )
    await message.answer(
        text,
        reply_markup=presenter.spin_keyboard(
            cost_cm=cfg.cost_cm,
            locale=effective_locale,
        ),
    )


@router.callback_query(F.data.startswith("roulette_free:"))
async def handle_roulette_callback(  # noqa: PLR0911 — каждая ветка отвечает за отдельный исход use-case-а; плоский switch уместен
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    spin_free_roulette: SpinFreeRoulette,
    balance: IBalanceConfig,
    bundle: IMessageBundle,
    locale: Locale | None = None,
    *,
    frame_delay_s: float = _DEFAULT_FRAME_DELAY_S,
) -> None:
    """Обработчик инлайн-кнопки `[Прокрутить]` под `/roulette_free`."""
    if tg_identity is None or callback.data is None or callback.message is None:
        return

    presenter = RoulettePresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    cost_cm = balance.get().roulette.free.cost_cm

    try:
        parse_roulette_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "roulette.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(
            presenter.toast_error(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    # Идемпотентность: один `callback.message.message_id` ⇒ одна
    # прокрутка. Повторный клик той же кнопки даст `SpinResult(idempotent=True)`.
    idempotency_key = f"msg:{callback.message.message_id}"

    # Снимаем клавиатуру до анимации, чтобы блокировать повторные клики
    # на UI-уровне даже если use-case ещё не вернул ответ.
    await _strip_keyboard(callback)

    # Анимация — 3 кадра через `edit_text`. Между кадрами — короткая
    # пауза. Любые ошибки edit-а проглатываем (anim — косметика).
    for frame in (1, 2, 3):
        await _set_message_text(
            callback,
            presenter.animation_frame(frame_index=frame, locale=effective_locale),
        )
        if frame < 3:
            await asyncio.sleep(frame_delay_s)

    try:
        result = await spin_free_roulette.execute(
            SpinFreeRouletteCommand(
                player_id=tg_identity.tg_user_id,
                idempotency_key=idempotency_key,
            )
        )
    except RouletteThicknessGateError as exc:
        await callback.answer(
            presenter.toast_thickness_gate(
                required=exc.required_level,
                actual=exc.thickness_level,
                locale=effective_locale,
            ),
            show_alert=True,
        )
        await _set_message_text(
            callback,
            presenter.requirement_thickness(
                required=exc.required_level,
                actual=exc.thickness_level,
                locale=effective_locale,
            ),
        )
        return
    except InsufficientLengthForRouletteError as exc:
        await callback.answer(
            presenter.toast_insufficient_length(
                required_cm=exc.cost_cm,
                actual_cm=exc.length_cm,
                locale=effective_locale,
            ),
            show_alert=True,
        )
        await _set_message_text(
            callback,
            presenter.requirement_length(
                required_cm=exc.cost_cm,
                actual_cm=exc.length_cm,
                locale=effective_locale,
            ),
        )
        return
    except PlayerNotFoundError:
        await callback.answer(
            presenter.toast_not_registered(locale=effective_locale),
            show_alert=True,
        )
        await _set_message_text(
            callback,
            presenter.not_registered(locale=effective_locale),
        )
        return
    except Exception:
        _LOGGER.exception(
            "roulette.callback: unexpected error",
            extra={"tg_id": tg_identity.tg_user_id, "data": callback.data},
        )
        await callback.answer(
            presenter.toast_error(locale=effective_locale),
            show_alert=False,
        )
        return

    if result.idempotent:
        await callback.answer(
            presenter.toast_already_processed(locale=effective_locale),
            show_alert=False,
        )
        await _set_message_text(
            callback,
            presenter.result_idempotent(locale=effective_locale),
        )
        return

    await callback.answer(
        presenter.toast_spin_complete(locale=effective_locale),
        show_alert=False,
    )
    await _set_message_text(
        callback,
        presenter.render_result(
            result=result,
            cost_cm=cost_cm,
            locale=effective_locale,
        ),
    )


async def _strip_keyboard(callback: CallbackQuery) -> None:
    """Снять inline-клавиатуру у сообщения, к которому привязан callback.

    Любые ошибки edit-а (старое сообщение, недоступное `InaccessibleMessage`)
    поглощаем — это не критично для UX.
    """
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug(
            "roulette.callback: failed to strip keyboard",
            extra={"chat_id": msg.chat.id if hasattr(msg, "chat") else None},
        )


async def _set_message_text(callback: CallbackQuery, text: str) -> None:
    """Заменить текст сообщения, к которому привязан callback.

    Аналогично `_strip_keyboard`: ошибки edit-а поглощаем, чтобы не
    падать на старых сообщениях / `InaccessibleMessage`.
    """
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_text(text)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug(
            "roulette.callback: failed to edit message text",
            extra={"chat_id": msg.chat.id if hasattr(msg, "chat") else None},
        )
