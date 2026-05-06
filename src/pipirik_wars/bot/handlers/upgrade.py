"""Handler команды `/upgrade` (Спринт 1.4.A → 1.5.D → 2.4.D, ГДД §3.2 + §13.1).

`/upgrade` (1.4.2) в ЛС:

1. Зовёт `GetProfile` use-case → берёт текущего игрока и его длину.
2. Считает стоимость следующего уровня по
   `progression.cost_for_upgrade(...)` через snapshot баланса.
3. Если списать нельзя по правилу 20 см (Спринт 1.2.1) — отвечает
   `UpgradePresenter.insufficient(...)`.
4. Иначе — отвечает карточкой `UpgradePresenter.proposal(...)` с
   инлайн-парой `[Подтвердить (X см)] [Отменить]` (подписи кнопок
   тоже локализованы).

Кнопки `[Подтвердить (X см)]` / `[Отменить]`:

- `confirm` — зовёт `UpgradeThickness` use-case с тем же
  `expected_cost_cm`, что был в callback_data. Если использован
  устаревший снимок баланса (между показом и нажатием был перегружен
  YAML), use-case бросает `ConcurrencyError`, handler шлёт
  `UpgradePresenter.race(...)`.
- `cancel` — handler снимает клавиатуру и отвечает
  `UpgradePresenter.cancelled(...)`.

В группе/супергруппе — инструкция «открой ЛС» (как у `/forest` и
`/profile`). 1.5.D убрал hardcoded `REPLY_*_RU`-константы и
`RENDER_UPGRADE_*`-строки: теперь всё идёт через `IMessageBundle`.

Реферальный milestone (Спринт 2.4.D, ГДД §13.1):
- После успешного `UpgradeThickness.execute(...)` handler зовёт
  `GrantReferralThicknessMilestone` для нового уровня толщины. Если
  у апгрейднувшегося нет реферальной записи — use-case вернёт
  `ReferralMilestoneNotApplicable` (no-op). Если milestone уже был
  выдан — бросит `MilestoneAlreadyGrantedError` (handler swallow-ит
  с логированием). Бонус рефереру (+10 на толщине 3, +30 на 5)
  выдаётся атомарно через `ILengthGranter`.
"""

from __future__ import annotations

import logging
from typing import Final

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.dto.inputs import (
    GrantReferralThicknessMilestoneInput,
    UpgradeThicknessInput,
)
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.player import GetProfile
from pipirik_wars.application.progression import UpgradeThickness
from pipirik_wars.application.referral import GrantReferralThicknessMilestone
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import (
    UpgradePresenter,
    parse_upgrade_callback_data,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.progression import (
    MIN_LENGTH_AFTER_SPEND_CM,
    AnticheatSoftBanError,
    InsufficientLengthError,
    cost_for_upgrade,
)
from pipirik_wars.domain.referral import MilestoneAlreadyGrantedError
from pipirik_wars.shared.errors import ConcurrencyError

router = Router(name="upgrade")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


@router.message(Command("upgrade"))
async def handle_upgrade(
    message: Message,
    tg_identity: TgIdentity | None,
    get_profile: GetProfile,
    balance: IBalanceConfig,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Команда `/upgrade` — показать карточку подтверждения прокачки."""
    presenter = UpgradePresenter(bundle=bundle)
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
    cfg = balance.get()
    cost_cm = cost_for_upgrade(
        current_thickness=player.thickness.level,
        cost_base=cfg.thickness.cost_base,
        cost_exponent=cfg.thickness.cost_exponent,
    )

    if player.length.cm - cost_cm < MIN_LENGTH_AFTER_SPEND_CM:
        deficit = MIN_LENGTH_AFTER_SPEND_CM - (player.length.cm - cost_cm)
        await message.answer(
            presenter.insufficient(
                current_thickness=player.thickness.level,
                cost_cm=cost_cm,
                current_length_cm=player.length.cm,
                deficit_cm=max(deficit, 1),
                min_after_spend_cm=MIN_LENGTH_AFTER_SPEND_CM,
                locale=effective_locale,
            )
        )
        return

    text = presenter.proposal(
        current_thickness=player.thickness.level,
        cost_cm=cost_cm,
        current_length_cm=player.length.cm,
        min_after_spend_cm=MIN_LENGTH_AFTER_SPEND_CM,
        locale=effective_locale,
    )
    await message.answer(
        text,
        reply_markup=presenter.proposal_keyboard(
            expected_cost_cm=cost_cm,
            locale=effective_locale,
        ),
    )


@router.callback_query(F.data.startswith("upgrade:"))
async def handle_upgrade_callback(  # noqa: PLR0911 — каждая ветка возврата = отдельная ошибка use-case-а, плоский switch уместен
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    upgrade_thickness: UpgradeThickness,
    grant_referral_thickness_milestone: GrantReferralThicknessMilestone,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Обработчик инлайн-кнопок `[Подтвердить] / [Отменить]` под /upgrade."""
    if tg_identity is None or callback.data is None or callback.message is None:
        return

    presenter = UpgradePresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parsed = parse_upgrade_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "upgrade.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(
            presenter.toast_race(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    if parsed.action == "cancel":
        await callback.answer(
            presenter.toast_cancelled(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        await _set_message_text(callback, presenter.cancelled(locale=effective_locale))
        return

    # action == "confirm"
    try:
        result = await upgrade_thickness.execute(
            UpgradeThicknessInput(
                tg_id=tg_identity.tg_user_id,
                expected_cost_cm=parsed.expected_cost_cm,
            )
        )
    except PlayerNotFoundError:
        await callback.answer(
            presenter.toast_player_not_found(locale=effective_locale),
            show_alert=True,
        )
        await _strip_keyboard(callback)
        return
    except InsufficientLengthError as exc:
        # Между показом карточки и нажатием Подтвердить игрок успел
        # потратить длину (другая активность). Показываем «короткую»
        # карточку без полной — handler не знает свежий thickness без
        # повторного `GetProfile`, а делать второй запрос ради
        # сообщения избыточно.
        await callback.answer(
            presenter.toast_insufficient(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        await _set_message_text(
            callback,
            presenter.insufficient_short(
                cost_cm=exc.cost_cm,
                current_length_cm=exc.length_cm,
                min_after_spend_cm=exc.min_after_spend_cm,
                deficit_cm=exc.deficit_cm,
                locale=effective_locale,
            ),
        )
        return
    except ConcurrencyError:
        await callback.answer(
            presenter.toast_race(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        await _set_message_text(callback, presenter.race(locale=effective_locale))
        return
    except AnticheatSoftBanError as exc:
        await callback.answer(
            presenter.toast_anticheat_blocked(locale=effective_locale),
            show_alert=True,
        )
        await _strip_keyboard(callback)
        await _set_message_text(
            callback,
            presenter.anticheat_blocked(
                banned_until=exc.banned_until.isoformat(),
                locale=effective_locale,
            ),
        )
        return

    # Реферальный milestone (Спринт 2.4.D): если апгрейднувшийся игрок
    # был приглашён по рефке — начислить milestone-бонус рефереру за
    # достижение толщины 3 / 5. Use-case сам проверяет: реферальная
    # запись существует, milestone не выдавался ранее, балансовая
    # точка совпадает с новым уровнем. Любые «no-op-кейсы» (рефки нет,
    # milestone уже выдан) тихо проглатываются — апгрейд для самого
    # игрока всё равно состоялся, и поломать UX дополнительной ошибкой
    # нельзя.
    try:
        await grant_referral_thickness_milestone.execute(
            GrantReferralThicknessMilestoneInput(
                referred_tg_id=tg_identity.tg_user_id,
                new_thickness_level=result.new_thickness,
            )
        )
    except MilestoneAlreadyGrantedError:
        # Re-delivery callback-а или повторный апгрейд после понижения.
        # Бизнес-инвариант: один milestone выдаётся ровно один раз.
        _LOGGER.info(
            "Referral milestone already granted: tg_id=%s, thickness=%s",
            tg_identity.tg_user_id,
            result.new_thickness,
        )

    await callback.answer(
        presenter.toast_upgraded(locale=effective_locale),
        show_alert=False,
    )
    await _strip_keyboard(callback)
    await _set_message_text(
        callback,
        presenter.success(
            new_thickness=result.new_thickness,
            cost_cm=result.cost_cm,
            new_length_cm=result.player_after.length.cm,
            locale=effective_locale,
        ),
    )


async def _strip_keyboard(callback: CallbackQuery) -> None:
    """Снять inline-клавиатуру у сообщения, к которому привязан callback.

    Делает повторное нажатие невозможным со стороны UI. Любые ошибки
    edit-а (старое сообщение, недоступное `InaccessibleMessage`)
    поглощаем — это не критично для UX.
    """
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug(
            "upgrade.callback: failed to strip keyboard",
            extra={"chat_id": msg.chat.id if hasattr(msg, "chat") else None},
        )


async def _set_message_text(callback: CallbackQuery, text: str) -> None:
    """Заменить текст сообщения, к которому привязан callback.

    Аналогично `_strip_keyboard`: ошибки edit-а поглощаем, чтобы не
    падать на старых сообщениях.
    """
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_text(text)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug(
            "upgrade.callback: failed to edit message text",
            extra={"chat_id": msg.chat.id if hasattr(msg, "chat") else None},
        )
