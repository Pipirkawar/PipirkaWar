"""Доменная подсистема DAU Gate (ГДД §18).

Содержит **порты** (интерфейсы) для:

- `IDauCounter` — счётчик уникальных активных игроков за сегодняшний
  игровой день (00:00 → 24:00 по `Europe/Moscow`).
- `IDauLimit` — runtime-управляемый лимит DAU (`MAX_DAU`).

Реализации — в `infrastructure/dau/` (in-memory с авто-сбросом по дате
МСК). Use-case-ы — в `application/dau/`.
"""

from pipirik_wars.domain.dau.ports import IDauCounter, IDauLimit

__all__ = ["IDauCounter", "IDauLimit"]
