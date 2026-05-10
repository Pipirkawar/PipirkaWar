"""Презентер `/roulette_free`-ветки (Спринт 3.5-D, ГДД §12.4).

Тонкий локализационный фасад над `IMessageBundle` для всех текстов
free-to-play рулетки:

* pre-spin карточка с подтверждением и кнопкой `[Прокрутить — N см]`,
* warning-карточки на gate-фейлах (толщина < 2, длина < 100),
* анимация прокрутки (3 кадра через `edit_text`),
* result-карточка для каждого `RouletteOutcomeKind`
  (LENGTH с дельтой см, ITEM/SCROLL_REGULAR/SCROLL_BLESSED как
  заглушки до Phase 4, CRYPTO_LOT — недостижимый при пустом крипто-пуле,
  но ключ присутствует для полноты),
* callback-toast-ы (gate-фейлы, идемпотентный retry, generic-error).

Сериализация `callback_data` (`roulette_free:spin`) живёт в этом же
модуле — одна точка истины для префикса. Действие одно (`spin`),
поэтому в `callback_data` нет ни id-сущности, ни payload-аргументов:
идемпотентность держит handler через `f"msg:{tg_message_id}"`-ключ
(`SpinFreeRouletteCommand.idempotency_key`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.roulette import SpinResult
from pipirik_wars.domain.roulette import RouletteOutcomeKind

_ROULETTE_CALLBACK_PREFIX: Final[str] = "roulette_free"

RouletteCallbackAction = Literal["spin"]
_VALID_ACTIONS: Final[frozenset[RouletteCallbackAction]] = frozenset({"spin"})

# Кадры анимации прокрутки. Handler по индексу подставляет
# `roulette-free-animation-frame-N` (1..ANIMATION_FRAMES_COUNT).
ANIMATION_FRAMES_COUNT: Final[int] = 3

_KEY_GROUP: Final[MessageKey] = MessageKey("roulette-free-group")
_KEY_OTHER: Final[MessageKey] = MessageKey("roulette-free-other")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("roulette-free-not-registered")
_KEY_REQUIREMENT_THICKNESS: Final[MessageKey] = MessageKey("roulette-free-requirement-thickness")
_KEY_REQUIREMENT_LENGTH: Final[MessageKey] = MessageKey("roulette-free-requirement-length")
_KEY_PROMPT: Final[MessageKey] = MessageKey("roulette-free-prompt")
_KEY_BUTTON_SPIN: Final[MessageKey] = MessageKey("roulette-free-button-spin")
_KEY_RESULT_LENGTH: Final[MessageKey] = MessageKey("roulette-free-result-length")
_KEY_RESULT_ITEM: Final[MessageKey] = MessageKey("roulette-free-result-item")
_KEY_RESULT_SCROLL_REGULAR: Final[MessageKey] = MessageKey("roulette-free-result-scroll-regular")
_KEY_RESULT_SCROLL_BLESSED: Final[MessageKey] = MessageKey("roulette-free-result-scroll-blessed")
_KEY_RESULT_CRYPTO_LOT: Final[MessageKey] = MessageKey("roulette-free-result-crypto-lot")
_KEY_RESULT_IDEMPOTENT: Final[MessageKey] = MessageKey("roulette-free-result-idempotent")
_KEY_TOAST_THICKNESS: Final[MessageKey] = MessageKey("roulette-free-toast-thickness-gate")
_KEY_TOAST_INSUFFICIENT: Final[MessageKey] = MessageKey("roulette-free-toast-insufficient-length")
_KEY_TOAST_NOT_REGISTERED: Final[MessageKey] = MessageKey("roulette-free-toast-not-registered")
_KEY_TOAST_SPIN_COMPLETE: Final[MessageKey] = MessageKey("roulette-free-toast-spin-complete")
_KEY_TOAST_ALREADY_PROCESSED: Final[MessageKey] = MessageKey(
    "roulette-free-toast-already-processed"
)
_KEY_TOAST_ERROR: Final[MessageKey] = MessageKey("roulette-free-toast-error")


@dataclass(frozen=True, slots=True)
class RouletteCallbackData:
    """Распаршенный `callback_data` инлайн-кнопки рулетки.

    Формат: `roulette_free:<action>`. На 3.5-D `action` всегда `spin`;
    структура оставлена расширяемой на случай добавления action-ов в
    Phase 4 (например, `claim` для CRYPTO_LOT-пула).
    """

    action: RouletteCallbackAction


def roulette_callback_data(*, action: RouletteCallbackAction) -> str:
    """Сериализовать `callback_data` инлайн-кнопки рулетки.

    Формат: `roulette_free:<action>` (≤ 64 байт; `roulette_free:spin`
    — 18 байт). Бросает `ValueError` на неизвестный action.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown roulette callback action: {action!r}")
    return f"{_ROULETTE_CALLBACK_PREFIX}:{action}"


def parse_roulette_callback_data(data: str) -> RouletteCallbackData:
    """Распарсить `callback_data` рулетки. На любой мусор — `ValueError`."""
    parts = data.split(":")
    if len(parts) != 2 or parts[0] != _ROULETTE_CALLBACK_PREFIX:
        raise ValueError(
            f"roulette callback_data must be 'roulette_free:<action>', got {data!r}",
        )
    _, action_raw = parts
    if action_raw == "spin":
        return RouletteCallbackData(action="spin")
    raise ValueError(f"unknown roulette action: {action_raw!r}")


def is_roulette_callback(data: str | None) -> bool:
    """Filter helper — это callback рулетки?

    Используется handler-ом через `F.data.startswith(...)`-фильтр,
    чтобы не пересекаться с `boss:` / `caravan:` / `enc:` / etc.
    """
    if data is None:
        return False
    return data.startswith(f"{_ROULETTE_CALLBACK_PREFIX}:")


class RoulettePresenter:
    """Локализованный рендер ответов `/roulette_free`-handler-а через `IMessageBundle`.

    Префикс ключей — `roulette-free-*`. Все методы — pure: ничего не
    пишут, не зовут I/O, только зовут `bundle.format(...)`.
    """

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- Команда `/roulette_free` — где её пускать / парсинг ---

    def group(self, *, locale: Locale) -> str:
        """Команда вызвана в групповом чате — направляем в личку."""
        return self._bundle.format(_KEY_GROUP, locale=locale)

    def other(self, *, locale: Locale) -> str:
        """Команда вызвана в канале / без identity — директива «только в личке»."""
        return self._bundle.format(_KEY_OTHER, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        """Игрок не нажимал /start — `PlayerNotFoundError`."""
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    # --- Команда `/roulette_free` — gate-warning-карточки в личке ---

    def requirement_thickness(
        self,
        *,
        required: int,
        actual: int,
        locale: Locale,
    ) -> str:
        """Толщина < `min_thickness_level` (ГДД §12.4.2 = 2)."""
        return self._bundle.format(
            _KEY_REQUIREMENT_THICKNESS,
            locale=locale,
            required=required,
            actual=actual,
        )

    def requirement_length(
        self,
        *,
        required_cm: int,
        actual_cm: int,
        locale: Locale,
    ) -> str:
        """Длина < `cost_cm` (ГДД §12.4.2 = 100 см)."""
        return self._bundle.format(
            _KEY_REQUIREMENT_LENGTH,
            locale=locale,
            required_cm=required_cm,
            actual_cm=actual_cm,
        )

    # --- Pre-spin карточка с inline-кнопкой `[Прокрутить — N см]` ---

    def prompt(
        self,
        *,
        current_length_cm: int,
        cost_cm: int,
        locale: Locale,
    ) -> str:
        """Карточка-приглашение: текущая длина + стоимость спина."""
        return self._bundle.format(
            _KEY_PROMPT,
            locale=locale,
            current_length_cm=current_length_cm,
            cost_cm=cost_cm,
            remaining_cm=current_length_cm - cost_cm,
        )

    def spin_keyboard(self, *, cost_cm: int, locale: Locale) -> InlineKeyboardMarkup:
        """Inline-клавиатура pre-spin карточки: одна кнопка `[Прокрутить — N см]`.

        `callback_data` инвариантна (`roulette_free:spin`) — payload-а нет;
        handler читает `cost_cm` повторно из конфига на момент клика
        (для рулетки race по стоимости не требуется как в `/upgrade`,
        потому что её менять под игроком не планируется и редактирование
        balance.yaml в проде делается через `BalanceReload` с явным
        admin-аудитом).
        """
        button = InlineKeyboardButton(
            text=self._bundle.format(_KEY_BUTTON_SPIN, locale=locale, cost_cm=cost_cm),
            callback_data=roulette_callback_data(action="spin"),
        )
        return InlineKeyboardMarkup(inline_keyboard=[[button]])

    # --- Анимация прокрутки (3 кадра через edit_text) ---

    def animation_frame(self, *, frame_index: int, locale: Locale) -> str:
        """Текст N-го кадра анимации (1-based, 1..ANIMATION_FRAMES_COUNT).

        Handler крутит `await msg.edit_text(...)` в цикле с задержкой,
        каждый кадр — отдельный locale-ключ
        `roulette-free-animation-frame-{1,2,3}`.
        """
        if not (1 <= frame_index <= ANIMATION_FRAMES_COUNT):
            raise ValueError(
                f"animation frame_index must be in [1, {ANIMATION_FRAMES_COUNT}], got "
                f"{frame_index}",
            )
        return self._bundle.format(
            MessageKey(f"roulette-free-animation-frame-{frame_index}"),
            locale=locale,
        )

    # --- Result-карточки по `RouletteOutcomeKind` ---

    def render_result(
        self,
        *,
        result: SpinResult,
        cost_cm: int,
        locale: Locale,
    ) -> str:
        """Главный диспетчер: `SpinResult` → текст result-карточки.

        Идемпотентный retry (`result.idempotent=True`) → `result_idempotent(...)`.
        Иначе по `outcome.kind` маршрутизация на конкретный result-метод.
        Падает `ValueError`, если use-case вернул `idempotent=False` и
        `outcome=None` (контракт `SpinResult`-а не должен такое допускать).
        """
        if result.idempotent:
            return self.result_idempotent(locale=locale)
        if result.outcome is None:
            raise ValueError(
                "SpinResult.outcome is None but idempotent=False — invariant violated",
            )
        kind = result.outcome.kind
        if kind is RouletteOutcomeKind.LENGTH:
            assert result.outcome.length_cm is not None
            return self.result_length(
                length_cm=result.outcome.length_cm,
                cost_cm=cost_cm,
                locale=locale,
            )
        if kind is RouletteOutcomeKind.ITEM:
            return self.result_item(cost_cm=cost_cm, locale=locale)
        if kind is RouletteOutcomeKind.SCROLL_REGULAR:
            return self.result_scroll_regular(cost_cm=cost_cm, locale=locale)
        if kind is RouletteOutcomeKind.SCROLL_BLESSED:
            return self.result_scroll_blessed(cost_cm=cost_cm, locale=locale)
        if kind is RouletteOutcomeKind.CRYPTO_LOT:
            return self.result_crypto_lot(cost_cm=cost_cm, locale=locale)
        # mypy исчерпал union — недостижимо, но guard для будущих kind-ов.
        raise ValueError(f"unknown RouletteOutcomeKind: {kind!r}")

    def result_length(
        self,
        *,
        length_cm: int,
        cost_cm: int,
        locale: Locale,
    ) -> str:
        """LENGTH-исход: игрок получает `+length_cm` см (ГДД §12.4.2)."""
        return self._bundle.format(
            _KEY_RESULT_LENGTH,
            locale=locale,
            length_cm=length_cm,
            cost_cm=cost_cm,
        )

    def result_item(self, *, cost_cm: int, locale: Locale) -> str:
        """ITEM-исход (заглушка, резолвится в Phase 4)."""
        return self._bundle.format(
            _KEY_RESULT_ITEM,
            locale=locale,
            cost_cm=cost_cm,
        )

    def result_scroll_regular(self, *, cost_cm: int, locale: Locale) -> str:
        """SCROLL_REGULAR-исход (заглушка, резолвится в Phase 4)."""
        return self._bundle.format(
            _KEY_RESULT_SCROLL_REGULAR,
            locale=locale,
            cost_cm=cost_cm,
        )

    def result_scroll_blessed(self, *, cost_cm: int, locale: Locale) -> str:
        """SCROLL_BLESSED-исход (заглушка, резолвится в Phase 4)."""
        return self._bundle.format(
            _KEY_RESULT_SCROLL_BLESSED,
            locale=locale,
            cost_cm=cost_cm,
        )

    def result_crypto_lot(self, *, cost_cm: int, locale: Locale) -> str:
        """CRYPTO_LOT-исход (на 3.5-D недостижим — pool пуст, ключ для полноты)."""
        return self._bundle.format(
            _KEY_RESULT_CRYPTO_LOT,
            locale=locale,
            cost_cm=cost_cm,
        )

    def result_idempotent(self, *, locale: Locale) -> str:
        """Идемпотентный retry (повторный клик той же spin-кнопки)."""
        return self._bundle.format(_KEY_RESULT_IDEMPOTENT, locale=locale)

    # --- Toast-ы (короткие inline-сообщения над callback-кнопкой) ---

    def toast_thickness_gate(
        self,
        *,
        required: int,
        actual: int,
        locale: Locale,
    ) -> str:
        """Toast: толщина < `min_thickness_level` (gate в callback-fire-flow)."""
        return self._bundle.format(
            _KEY_TOAST_THICKNESS,
            locale=locale,
            required=required,
            actual=actual,
        )

    def toast_insufficient_length(
        self,
        *,
        required_cm: int,
        actual_cm: int,
        locale: Locale,
    ) -> str:
        """Toast: длина < `cost_cm` (gate в callback-fire-flow)."""
        return self._bundle.format(
            _KEY_TOAST_INSUFFICIENT,
            locale=locale,
            required_cm=required_cm,
            actual_cm=actual_cm,
        )

    def toast_not_registered(self, *, locale: Locale) -> str:
        """Toast: игрок не зарегистрирован — нажми /start."""
        return self._bundle.format(_KEY_TOAST_NOT_REGISTERED, locale=locale)

    def toast_spin_complete(self, *, locale: Locale) -> str:
        """Toast: прокрутка успешно завершена."""
        return self._bundle.format(_KEY_TOAST_SPIN_COMPLETE, locale=locale)

    def toast_already_processed(self, *, locale: Locale) -> str:
        """Toast: повторный клик spin-кнопки — уже обработано."""
        return self._bundle.format(_KEY_TOAST_ALREADY_PROCESSED, locale=locale)

    def toast_error(self, *, locale: Locale) -> str:
        """Toast: общая ошибка (мусорный callback_data, неизвестная action)."""
        return self._bundle.format(_KEY_TOAST_ERROR, locale=locale)


__all__ = [
    "ANIMATION_FRAMES_COUNT",
    "RouletteCallbackAction",
    "RouletteCallbackData",
    "RoulettePresenter",
    "is_roulette_callback",
    "parse_roulette_callback_data",
    "roulette_callback_data",
]
