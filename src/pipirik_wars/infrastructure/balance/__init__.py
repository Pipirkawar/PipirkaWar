"""Infrastructure-слой для балансовой конфигурации.

`YamlBalanceLoader` — реализация `IBalanceConfig`, которая читает
`config/balance.yaml`, валидирует его pydantic-схемой и держит снимок
в памяти. Поддерживает hot-reload через `reload()`.
"""

from pipirik_wars.infrastructure.balance.loader import YamlBalanceLoader

__all__ = ["YamlBalanceLoader"]
