"""Каталог забавных логов леса (ГДД §15, ПД 1.5.3).

`ForestLogTemplate` — иммутабельная запись каталога flavour-сообщений
леса: стабильный `id` (используется в audit-логе и аналитике «какой
шаблон выпал чаще») и текст с опциональными плейсхолдерами `{user}`
и `{delta}`. Шаблоны хранятся в `config/templates/forest_logs_<locale>.json`
и загружаются infrastructure-адаптером `JsonForestLogTemplateProvider`.

`pick_forest_log_template(*, random, templates)` — чистая функция выбора
одного шаблона. Без I/O. Используется use-case-ом `FinishForestRun`
для добавления flavour-строки в сообщение «вернулся из леса».

Подстановка плейсхолдеров — задача bot-presenter-а: домен возвращает
сырой `template.text`, presenter заменяет `{user}` на полный ник и
`{delta}` на «+N см».
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pipirik_wars.domain.forest.errors import ForestLogNoTemplatesError
from pipirik_wars.domain.shared.ports import IRandom


@dataclass(frozen=True, slots=True)
class ForestLogTemplate:
    """Один шаблон забавного лога леса (ГДД §15).

    Поля:
    - `id` — стабильный машинный идентификатор (например,
      ``"forest.ru.0007"``). Используется для audit-логов и аналитики.
    - `text` — текст лога. Может содержать плейсхолдеры ``{user}``
      (полный ник «Титул Название Имя») и ``{delta}`` (+N см).
    """

    id: str
    text: str

    def __post_init__(self) -> None:
        if not self.id or self.id != self.id.strip():
            raise ValueError(f"ForestLogTemplate.id must be non-empty, got {self.id!r}")
        if not self.text or self.text != self.text.strip():
            raise ValueError(f"ForestLogTemplate.text must be non-empty, got {self.text!r}")


def pick_forest_log_template(
    *,
    random: IRandom,
    templates: Sequence[ForestLogTemplate],
) -> ForestLogTemplate:
    """Выбрать один шаблон из каталога. Без I/O.

    Pre: `templates` непуст (иначе `ForestLogNoTemplatesError` — это
    ошибка деплоя, prod-инвариант: каталог не пуст).
    """
    if not templates:
        raise ForestLogNoTemplatesError()
    return random.choice(list(templates))


__all__ = ["ForestLogTemplate", "pick_forest_log_template"]
