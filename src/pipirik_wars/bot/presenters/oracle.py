"""Презентер для команды `/oracle` (Спринт 1.4.B → 1.5.D → 3.6-B; ГДД §11, §11.1).

Тонкий слой между use-case `InvokeOracle` и Telegram-handler-ом.
С 1.5.D переехал на `IMessageBundle`: handler шлёт `OraclePresenter`-у
строки локализованных ключей `oracle-*` (см. `locales/{ru,en}.ftl`).

Спринт 3.6-B расширил `success(...)` под бонус-за-племена (ГДД §11.1):
вместо одной строки «+N см» презентер собирает **до трёх строк** —
`oracle-base-line` (всегда), `oracle-tribe-bonus-line` (только при
`n_active_tribes > 0`, c Fluent-плюрал-формами) и `oracle-total-line`
(тоже только при `n_active_tribes > 0`, иначе `base == total`).

Презентер отвечает за два I/O-side-effect-free аспекта:

1. **Локализация** — берёт строки из `IMessageBundle` по ключу
   и подставляет параметры (`$base_cm`, `$tribe_bonus_cm`,
   `$n_active_tribes`, `$total_cm`, `$new_length_cm` и т.п.).
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
_KEY_SUCCESS_PREDICTION: Final[MessageKey] = MessageKey("oracle-success-prediction")
_KEY_BASE_LINE: Final[MessageKey] = MessageKey("oracle-base-line")
_KEY_TRIBE_BONUS_LINE: Final[MessageKey] = MessageKey("oracle-tribe-bonus-line")
_KEY_TOTAL_LINE: Final[MessageKey] = MessageKey("oracle-total-line")
_KEY_NEW_LENGTH_LINE: Final[MessageKey] = MessageKey("oracle-new-length-line")
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
        base_cm: int,
        tribe_bonus_cm: int,
        n_active_tribes: int,
        new_length_cm: int,
        user_display: str,
        locale: Locale,
    ) -> str:
        """Сообщение успеха: предсказание + базовый бонус + (опц.) бонус-за-племена
        + (опц.) итог + новая длина (Спринт 3.6-B / ГДД §11, §11.1).

        Структура ответа:

        1. Шапка (`oracle-success-prediction`) — «🔮 Предсказание дня:» + текст
           шаблона с подставленным `{user}`.
        2. Пустая строка-разделитель.
        3. `oracle-base-line` — всегда («📏 +N см — базовая»).
        4. `oracle-tribe-bonus-line` — **только** если `n_active_tribes > 0`
           (Fluent-плюрал-формы по `n_active_tribes`).
        5. `oracle-total-line` — **только** если `n_active_tribes > 0`
           (иначе `base_cm == total_cm` и строка избыточна).
        6. `oracle-new-length-line` — всегда («Теперь у тебя: M см»).

        Параметры:
        - `template_text` — сырой шаблон предсказания (с возможным `{user}`);
        - `base_cm` — базовый бросок 1..20 см (без бонуса-за-племена);
        - `tribe_bonus_cm` — бонус-за-племена; 0, если фичефлаг выключен или
          у игрока нет квалифицированных племён;
        - `n_active_tribes` — сколько активных племён засчитано (определяет
          плюрал-форму и видимость строк tribe/total);
        - `new_length_cm` — новая длина игрока (с учётом anti-cheat-клампа);
        - `user_display` — имя/`@username` для подстановки `{user}`;
        - `locale` — локаль ответа (RU/EN).
        """
        prediction = _render_template(template_text, user=user_display)
        lines: list[str] = [
            self._bundle.format(
                _KEY_SUCCESS_PREDICTION,
                locale=locale,
                prediction=prediction,
            ),
            "",
            self._bundle.format(
                _KEY_BASE_LINE,
                locale=locale,
                base_cm=base_cm,
            ),
        ]
        if n_active_tribes > 0:
            lines.append(
                self._bundle.format(
                    _KEY_TRIBE_BONUS_LINE,
                    locale=locale,
                    tribe_bonus_cm=tribe_bonus_cm,
                    n_active_tribes=n_active_tribes,
                )
            )
            lines.append(
                self._bundle.format(
                    _KEY_TOTAL_LINE,
                    locale=locale,
                    total_cm=base_cm + tribe_bonus_cm,
                )
            )
        lines.append(
            self._bundle.format(
                _KEY_NEW_LENGTH_LINE,
                locale=locale,
                new_length_cm=new_length_cm,
            )
        )
        return "\n".join(lines)

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
