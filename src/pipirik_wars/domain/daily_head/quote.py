"""Domain-сущность каталога цитат «Главы клана дня» (Спринт 2.3.D).

`ClanQuoteTemplate` — иммутабельная запись каталога цитат:
стабильный `id` (используется в `audit_log` и для аналитики «какие
цитаты выпадают чаще»), текст с опциональным плейсхолдером `{user}`
и кортеж тегов стилистики (`statham`, `vk_pablik`, `auf`, `meme`,
`profanity`).

Каталог хранится в `config/templates/clan_quotes_<locale>.json` и
загружается infrastructure-адаптером `JsonClanQuoteTemplateProvider`
(см. Спринт 2.3.D). Применяется handler-ом `/clan_head` (Спринт 2.3.E)
при рендере карточки-коронации главы клана дня.

Тег `profanity` помечает цитаты с лёгким матом. Фильтр по этому тегу —
задача handler/use-case-уровня (`balance.daily_head.content_policy.
mild_profanity` в Спринте 2.3.E); сам каталог хранит цитаты «как есть».
"""

from __future__ import annotations

from dataclasses import dataclass

ALLOWED_QUOTE_TAGS: frozenset[str] = frozenset(
    {
        "statham",
        "vk_pablik",
        "auf",
        "meme",
        "profanity",
    }
)
"""Whitelist тегов стилистики цитат (см. ПД §5 / Спринт 2.3.4).

- ``statham`` — цитаты в стиле «по понятиям» / Стэтхем-меметика.
- ``vk_pablik`` — паблик-цитаты ВК (типографика, эмоции, абсурд).
- ``auf`` — АУФ-волчья мудрость.
- ``meme`` — общеинтернетная мемная стилистика.
- ``profanity`` — содержит лёгкий мат (фильтруется через
  ``balance.daily_head.content_policy.mild_profanity`` в use-case-е 2.3.E).
"""


@dataclass(frozen=True, slots=True)
class ClanQuoteTemplate:
    """Один шаблон цитаты для коронации главы клана дня.

    Поля:
    - ``id`` — стабильный машинный идентификатор
      (например, ``"clan_quote.ru.0001"``). Сохраняется в
      ``audit_log.payload.quote_id`` (Спринт 2.3.E), используется для
      аналитики и для воспроизводимости тестов; не должен меняться
      между деплоями.
    - ``text`` — текст цитаты. Может содержать плейсхолдер ``{user}``
      для подстановки имени/ника главы клана.
    - ``tags`` — кортеж тегов из ``ALLOWED_QUOTE_TAGS``. Минимум один
      «стилистический» тег обязателен (``statham`` / ``vk_pablik`` /
      ``auf`` / ``meme``); ``profanity`` — опциональный модификатор.
    """

    id: str
    text: str
    tags: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.id or self.id != self.id.strip():
            raise ValueError(
                f"ClanQuoteTemplate.id must be non-empty trimmed string, got {self.id!r}",
            )
        if not self.text or self.text != self.text.strip():
            raise ValueError(
                f"ClanQuoteTemplate.text must be non-empty trimmed string, got {self.text!r}",
            )
        if len(self.tags) == 0:
            raise ValueError(
                f"ClanQuoteTemplate.tags must contain at least one style tag, got empty tuple "
                f"(id={self.id!r})",
            )
        unknown = set(self.tags) - ALLOWED_QUOTE_TAGS
        if unknown:
            raise ValueError(
                f"ClanQuoteTemplate.tags contains unknown tags {sorted(unknown)!r} "
                f"(id={self.id!r}); allowed: {sorted(ALLOWED_QUOTE_TAGS)!r}",
            )
        if len(self.tags) != len(set(self.tags)):
            raise ValueError(
                f"ClanQuoteTemplate.tags must be unique, got {self.tags!r} (id={self.id!r})",
            )
        # Хотя бы один «стилистический» тег обязателен
        # (`profanity` сам по себе — модификатор, без стиля цитата
        # не классифицируется по ПД §5 / 2.3.4).
        style_tags = set(self.tags) & (ALLOWED_QUOTE_TAGS - {"profanity"})
        if not style_tags:
            raise ValueError(
                f"ClanQuoteTemplate.tags must contain at least one style tag from "
                f"{sorted(ALLOWED_QUOTE_TAGS - {'profanity'})!r}, got {self.tags!r} "
                f"(id={self.id!r})",
            )

    @property
    def has_profanity(self) -> bool:
        """``True`` если цитата помечена тегом ``profanity``."""
        return "profanity" in self.tags


__all__ = [
    "ALLOWED_QUOTE_TAGS",
    "ClanQuoteTemplate",
]
