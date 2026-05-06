"""infrastructure/templates package — адаптеры файловых каталогов
(JSON / Fluent). На MVP-фазе:

- `JsonOracleTemplateProvider` — каталог предсказаний (Спринт 1.4.B).
- `JsonForestLogTemplateProvider` — каталог забавных логов леса
  (Спринт 1.5.G, ГДД §15).
- `JsonDuelLogTemplateProvider` — каталог забавных раунд-логов PvP
  (Спринт 2.1.H, ГДД §15).
- `JsonClanQuoteTemplateProvider` — каталог иронично-смешных цитат
  «Главы клана дня» (Спринт 2.3.D, ГДД §6.1 / ПД §5).
"""

from pipirik_wars.infrastructure.templates.clan_quotes import JsonClanQuoteTemplateProvider
from pipirik_wars.infrastructure.templates.duel_log import JsonDuelLogTemplateProvider
from pipirik_wars.infrastructure.templates.forest_log import JsonForestLogTemplateProvider
from pipirik_wars.infrastructure.templates.oracle import JsonOracleTemplateProvider

__all__ = [
    "JsonClanQuoteTemplateProvider",
    "JsonDuelLogTemplateProvider",
    "JsonForestLogTemplateProvider",
    "JsonOracleTemplateProvider",
]
