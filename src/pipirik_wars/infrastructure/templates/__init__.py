"""infrastructure/templates package — адаптеры файловых каталогов
(JSON / Fluent). На MVP-фазе:

- `JsonOracleTemplateProvider` — каталог предсказаний (Спринт 1.4.B).
- `JsonForestLogTemplateProvider` — каталог забавных логов леса
  (Спринт 1.5.G, ГДД §15).
"""

from pipirik_wars.infrastructure.templates.forest_log import JsonForestLogTemplateProvider
from pipirik_wars.infrastructure.templates.oracle import JsonOracleTemplateProvider

__all__ = [
    "JsonForestLogTemplateProvider",
    "JsonOracleTemplateProvider",
]
