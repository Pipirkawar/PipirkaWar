"""Порт репозитория истории `/oracle`.

`IOracleHistoryRepository` отвечает за таблицу `oracle_invocations` —
суточный «лог», по которому use-case `InvokeOracle` решает, можно ли
сегодня звать предсказателя.

Все методы исполняются внутри активного `IUnitOfWork`; собственный
коммит репозиторий не делает (правило Спринта 0.2).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class OracleInvocation:
    """Запись `oracle_invocations` — один вызов `/oracle` игроком.

    `moscow_date` — календарная дата по Москве в момент вызова.
    Уникальна вместе с `player_id` (БД-инвариант, см. миграцию
    `0005_oracle_invocations`): двух записей с тем же ключом быть
    не может, что и охраняет суточный кулдаун от race-кондишена.

    `template_id` хранится для аналитики «какие шаблоны выпадают
    чаще» и audit-логов. Сам текст шаблона тут не сохраняем —
    каталог шаблонов и есть источник правды.
    """

    player_id: int
    moscow_date: date
    bonus_cm: int
    template_id: str
    occurred_at: datetime


class IOracleHistoryRepository(abc.ABC):
    """Доступ к таблице `oracle_invocations`."""

    @abc.abstractmethod
    async def add(self, invocation: OracleInvocation) -> None:
        """Записать новый вызов `/oracle`.

        При попытке записать второй вызов на тот же `(player_id,
        moscow_date)` репо обязан бросить `IntegrityError` (БД-уровня
        UNIQUE-индекс). Use-case это перехватывает и трактует как
        race-вариант `OracleAlreadyUsedTodayError`.
        """

    @abc.abstractmethod
    async def get_for_day(
        self,
        *,
        player_id: int,
        moscow_date: date,
    ) -> OracleInvocation | None:
        """Вернуть запись `(player_id, moscow_date)`, либо `None`.

        Используется как preflight-проверка кулдауна **до** попытки
        вставки. Race-кондишен с ней совместим: даже если два запроса
        прошли preflight одновременно, БД-инвариант `add()`-а не даст
        вставить второй.
        """


__all__ = [
    "IOracleHistoryRepository",
    "OracleInvocation",
]
