"""Презентер для команды `/oracle` (Спринт 1.4.B → 1.5.D, ГДД §11).

Тонкий слой между use-case `InvokeOracle` и Telegram-handler-ом.
С 1.5.D переехал на `IMessageBundle`: handler шлёт `OraclePresenter`-у
строки локализованных ключей `oracle-*` (см. `locales/{ru,en}.ftl`).

Презентер отвечает за два I/O-side-effect-free аспекта:

1. **Локализация** — берёт строки из `IMessageBundle` по ключу
   и подставляет параметры (`$bonus_cm`, `$new_length_cm` и т.п.).
2. **Подстановка `{ user }` в шаблон предсказания** — текст шаблона
   (например, «{ user }, сегодня твоя длина будет…») приходит из
   каталога `templates/oracle_*.json` и сам по себе уже локализован,
   но `{ user }`-плейсхолдер заполняет именно презентер. Используется
   `_SafeDict`, чтобы шаблон с непредусмотренным `{ foo }` не падал
   с `KeyError`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey

# Username-плейсхолдер: подменяем `{user}` в шаблоне на актуальное имя
# игрока (или его @username). Если в шаблоне нет `{user}` — `format_map`
# вернёт текст as-is.
_USER_PLACEHOLDER: Final[str] = "user"

_KEY_GROUP: Final[MessageKey] = MessageKey("oracle-group")
_KEY_OTHER: Final[MessageKey] = MessageKey("oracle-other")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("oracle-not-registered")
_KEY_SUCCESS: Final[MessageKey] = MessageKey("oracle-success")
_KEY_ALREADY_USED: Final[MessageKey] = MessageKey("oracle-already-used")


class _SafeDict(dict[str, str]):
    """Dict, который для отсутствующих ключей возвращает их же
    в фигурных скобках. Защита от шаблонов, где `{user}` нет, или
    где в тексте оказался непредусмотренный плейсхолдер.
    """

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_template(text: str, *, user: str) -> str:
    """Подставить `{user}` (и возможные другие безопасные плейсхолдеры)."""
    return text.format_map(_SafeDict({_USER_PLACEHOLDER: user}))


class OraclePresenter:
    """Локализованный фасад над `IMessageBundle` для команды `/oracle`.

    Все методы возвращают готовый-к-отправке текст; handler делает
    `message.answer(presenter.success(...))`.
    """

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def group(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GROUP, locale=locale)

    def other(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_OTHER, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    def success(
        self,
        *,
        template_text: str,
        bonus_cm: int,
        new_length_cm: int,
        user_display: str,
        locale: Locale,
    ) -> str:
        """Сообщение успеха: предсказание + бонус + новая длина."""
        prediction = _render_template(template_text, user=user_display)
        return self._bundle.format(
            _KEY_SUCCESS,
            locale=locale,
            prediction=prediction,
            bonus_cm=bonus_cm,
            new_length_cm=new_length_cm,
        )

    def already_used(
        self,
        *,
        moscow_date: date,
        now: datetime,
        locale: Locale,
    ) -> str:
        """Сообщение «возвращайся завтра».

        Считает время до сброса (00:00 МСК следующего дня) на основе
        `now` и подставляет его в шаблон `oracle-already-used`.
        """
        hours, minutes = _hours_minutes_until_next_reset(moscow_date=moscow_date, now=now)
        return self._bundle.format(
            _KEY_ALREADY_USED,
            locale=locale,
            hours=hours,
            minutes=f"{minutes:02d}",
        )


def _hours_minutes_until_next_reset(*, moscow_date: date, now: datetime) -> tuple[int, int]:
    """Сколько часов/минут осталось до 00:00 МСК следующего дня."""
    moscow_tz = ZoneInfo("Europe/Moscow")
    now_moscow = now.replace(tzinfo=moscow_tz) if now.tzinfo is None else now.astimezone(moscow_tz)
    next_reset = datetime.combine(
        moscow_date + timedelta(days=1),
        datetime.min.time(),
        tzinfo=moscow_tz,
    )
    delta = next_reset - now_moscow
    if delta.total_seconds() < 0:
        delta = timedelta(0)
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    return hours, minutes


__all__ = ["OraclePresenter"]
