"""bot/filters package.

Aiogram-фильтры (`BaseFilter`-наследники), которые применяются
**на уровне router-а** для тихого отбрасывания апдейтов, не подходящих
под router. В отличие от middleware-ов, фильтры не имеют доступа к
обработке апдейта — они просто решают, попадает ли апдейт в этот
router или нет.
"""

from pipirik_wars.bot.filters.admin import IsAdminFilter

__all__ = ["IsAdminFilter"]
