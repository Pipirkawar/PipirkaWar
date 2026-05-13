"""Порт ИИ-генерации текста для предсказаний и логов (Спринт 4.1-M, задача 4.1.13).

Определяет абстрактный интерфейс `IAiTextGenerator`, который
инфраструктурный слой реализует через OpenAI API (или другой LLM-провайдер).

Контракт:
- Все методы — async (сетевой I/O к LLM-провайдеру).
- Возвращают `Sequence[str]` — список сгенерированных текстов.
- При недоступности LLM или ошибках — бросают `AiGenerationError`.
- Тексты содержат плейсхолдер `{user}` там, где шаблон должен
  персонализироваться по имени игрока.

Адаптер отвечает за:
- Prompt-engineering (системные инструкции, стиль, безопасность контента).
- Ретраи при transient-ошибках (rate-limit, timeout).
- Формат ответа (парсинг JSON-списка текстов из LLM-response).

Caller (background-task в bot/main.py) отвечает за:
- Вызов `generate_*` периодически (каждые N часов) или при пустом кэше.
- Запись результатов в in-memory-кэш провайдера (`AiOracleTemplateProvider._cache`).
- Обработку `AiGenerationError` (логирование + fallback на static templates).
"""

from __future__ import annotations

import abc
from collections.abc import Sequence
from typing import Literal

DuelLogKind = Literal["both_hit", "single_hit", "both_blocked"]
"""Категория исхода раунда дуэли для подбора flavour-шаблона.

Совпадает со строковыми значениями `domain.pvp.log_template.RoundOutcomeKind`
(порт не импортирует домен-перечисление явно, чтобы остаться
лёгким для тестов). Адаптер / провайдер отвечают за конверсию.
"""


class AiGenerationError(Exception):
    """LLM-провайдер недоступен или вернул невалидный ответ."""


class IAiTextGenerator(abc.ABC):
    """Абстрактный порт генерации текста через LLM.

    Реализации: `OpenAiTextGenerator` (infrastructure/ai/).
    Тесты: `FakeAiTextGenerator` (tests/conftest.py или inline).
    """

    @abc.abstractmethod
    async def generate_oracle_predictions(
        self,
        *,
        locale: str,
        count: int,
    ) -> Sequence[str]:
        """Сгенерировать `count` предсказаний Оракула для данной локали.

        Каждое предсказание — 1-2 предложения в мистическом/ироничном
        стиле. Обязательно содержит `{user}` — плейсхолдер для имени
        игрока (подставляется handler-ом при рендере).

        Пример (ru): "Сегодня твоя аура сияет ярче обычного, {user}.
        Вселенная готовит тебе щедрый подарок."
        """

    @abc.abstractmethod
    async def generate_forest_logs(
        self,
        *,
        locale: str,
        count: int,
    ) -> Sequence[str]:
        """Сгенерировать `count` логов похода в Лес.

        Каждый лог — 1-3 предложения, описывающие мини-приключение
        пипирика в лесу. Стиль: юмористический, с элементами фэнтези.
        Содержит `{user}` — имя игрока.

        Пример (ru): "{user} пробрался через густой папоротник и нашёл
        под корнями старого дуба мерцающий кристалл длины."
        """

    @abc.abstractmethod
    async def generate_duel_logs(
        self,
        *,
        locale: str,
        count: int,
        kind: DuelLogKind,
    ) -> Sequence[str]:
        """Сгенерировать `count` логов дуэли (PvP) категории `kind`.

        Каждый лог — 1-2 предложения, описывающие ход раунда.
        Плейсхолдеры зависят от `kind`:

        - `both_hit` / `both_blocked` — оба игрока равноправны, `{p1}` + `{p2}`.
        - `single_hit` — один пробил, второй заблокировал,
          `{attacker}` + `{defender}`.

        Пример (ru, both_hit): "{p1} и {p2} обменялись выпадами — оба
        вернулись в мятый воротник."
        """


__all__ = ["AiGenerationError", "DuelLogKind", "IAiTextGenerator"]
