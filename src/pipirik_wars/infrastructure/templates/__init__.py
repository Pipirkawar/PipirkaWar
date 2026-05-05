"""infrastructure/templates package — адаптеры файловых каталогов
(JSON / Fluent). Сейчас реализован только JSON-провайдер для
`/oracle` (Спринт 1.4.B); fluent-локализатор появится в 1.5.
"""

from pipirik_wars.infrastructure.templates.oracle import JsonOracleTemplateProvider

__all__ = ["JsonOracleTemplateProvider"]
