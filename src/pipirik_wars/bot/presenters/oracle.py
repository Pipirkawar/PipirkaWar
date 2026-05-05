"""Презентер для команды `/oracle` (Спринт 1.4.B, ГДД §11).

Тонкий слой рендеринга для bot-handler-а:

- **`render_oracle_success(...)`** — текст после успешного `/oracle`:
  предсказание + прибавка длины + новая длина.
- **`render_oracle_already_used(...)`** — текст при попытке вызвать
  `/oracle` дважды за один московский день (отдаёт время до сброса
  в 00:00 МСК).
- **`render_oracle_not_registered`** — отказ для незарегистрированного
  игрока.

Презентеры — чистые функции без I/O, тестируются изолированно.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

# Username-плейсхолдер: подменяем `{user}` в шаблоне на актуальное имя
# игрока (или его @username). Если в шаблоне нет `{user}` — `format_map`
# вернёт текст as-is.
_USER_PLACEHOLDER: Final[str] = "user"

REPLY_GROUP_RU: Final[str] = (
    "🔮 Команда /oracle доступна только в личке бота. Открой приватный чат и повтори."
)
REPLY_OTHER_RU: Final[str] = "🔮 Команда /oracle доступна только в личке бота."
REPLY_NOT_REGISTERED_RU: Final[str] = (
    "🔮 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате, и тогда "
    "предсказатель тебя услышит."
)


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


def render_oracle_success(
    *,
    template_text: str,
    bonus_cm: int,
    new_length_cm: int,
    user_display: str,
) -> str:
    """Сообщение успеха: предсказание + бонус + новая длина."""
    rendered = _render_template(template_text, user=user_display)
    return (
        f"🔮 Предсказание дня:\n{rendered}\n\n📏 +{bonus_cm} см\nТеперь у тебя: {new_length_cm} см"
    )


def render_oracle_already_used(
    *,
    moscow_date: date,
    now: datetime,
) -> str:
    """Сообщение «возвращайся завтра».

    Считает время до сброса (00:00 МСК следующего дня) на основе
    `now` и возвращает «через ~Xч Yм».
    """
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
    return (
        "🔮 Сегодня ты уже был у предсказателя.\n"
        f"Возвращайся через {hours}ч {minutes:02d}м (00:00 по Москве)."
    )


__all__ = [
    "REPLY_GROUP_RU",
    "REPLY_NOT_REGISTERED_RU",
    "REPLY_OTHER_RU",
    "render_oracle_already_used",
    "render_oracle_success",
]
