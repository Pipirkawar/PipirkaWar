"""Репозиторий игроков (порт)."""

from __future__ import annotations

import abc
from collections.abc import Sequence
from dataclasses import dataclass

from pipirik_wars.domain.player.entities import Player


@dataclass(frozen=True, slots=True)
class BroadcastRecipient:
    """Минимальная запись «кому отправлять» для broadcast (Спринт 2.5-D.4).

    Намеренно меньше `Player`-сущности, потому что для рассылки не нужны
    игровые поля (длина / толщина / клан) — нужны только адрес доставки
    (`tg_id`) и фактическая локаль (для статистики `failed_count` по
    локалям, если когда-нибудь понадобится). Чтобы не тащить весь
    `Player` через границу use-case → notifier и не аллоцировать
    объекты на десятки тысяч игроков (на масштабе MVP — единицы тысяч,
    но всё равно лишний overhead).

    `effective_locale` — это `locale_override or DEFAULT_LOCALE.code`
    (см. `application/i18n/locale.py`). Резолвится **на стороне репо**,
    чтобы use-case не дублировал fallback-логику.
    """

    tg_id: int
    effective_locale: str


class IPlayerRepository(abc.ABC):
    """Доступ к таблице `users`.

    Все методы исполняются внутри активной транзакции `IUnitOfWork`;
    собственный коммит репозиторий не делает (правило Спринта 0.2,
    единый источник коммита — UoW). При нарушении уникальности
    `tg_id` репозиторий бросает `PlayerAlreadyRegisteredError`.
    """

    @abc.abstractmethod
    async def get_by_tg_id(self, tg_id: int) -> Player | None:
        """Найти игрока по Telegram-ID или вернуть `None`."""

    @abc.abstractmethod
    async def get_by_id(self, *, player_id: int) -> Player | None:
        """Найти игрока по внутреннему `id`, либо вернуть `None`.

        Используется в use-case-ах, которые загружают игрока по
        `player_id`, а не по `tg_id` (например, `FinishForestRun`
        получает `player_id` из `forest_runs`).
        """

    @abc.abstractmethod
    async def add(self, player: Player) -> Player:
        """Добавить нового игрока. Возвращает копию с проставленным `id`.

        Для уже существующего `tg_id` бросает
        `PlayerAlreadyRegisteredError` (см. `domain.player.errors`).
        """

    @abc.abstractmethod
    async def save(self, player: Player) -> Player:
        """Обновить запись по `id`. Возвращает «канонический» инстанс,
        каким он лёг в БД (с обновлённым `updated_at`, если БД его
        перепишет server-side).

        Для несуществующего `id` бросает `IntegrityError`.
        """

    @abc.abstractmethod
    async def find_by_query(self, *, query: str, limit: int) -> Sequence[Player]:
        """Поиск игроков по свободному тексту (Спринт 2.5-B.1, ГДД §18.6.5).

        Семантика (по убыванию приоритета — выбираем **первую сработавшую** ветку,
        чтобы избежать дублей):

        * `query` — целое число → точное совпадение по `tg_id`. Возвращает 0 или 1
          игрока (ключ уникален).
        * `query` начинается с `@` и за ним идёт валидный username — точное
          совпадение по `users.username` (без `@`).
        * Иначе — case-insensitive substring (`ILIKE %query%`) по `users.username`
          и in-game `users.name` (что есть). Это покрывает кейс «помню часть
          @-шки» и «помню часть имени персонажа» (ГДД §2.4 / §2.5). Telegram
          `tg_full_name` (first/last) у нас в схеме не хранится — это
          по запросу можно добавить отдельной миграцией; пока не поддержано.

        Сортировка: `id ASC` (стабильный порядок). `limit` обязан быть
        положительным; адаптер не обязан валидировать ноль/негатив — это
        контракт уровня use-case.

        Замороженные / забаненные игроки **включаются** в результат (для админа
        они тоже валидные «таргеты» — заморозить / разморозить / разбанить).
        """

    @abc.abstractmethod
    async def list_top_by_length(self, *, limit: int) -> Sequence[Player]:
        """Топ-`limit` игроков по убыванию `length_cm` (ГДД §2.6, ПД 1.4.6).

        Возвращает только `ACTIVE`-игроков (замороженные исключаются —
        они не «играют»). Тай-брейкер при равной длине — `id ASC`,
        чтобы порядок был стабильным от запроса к запросу.

        `limit` обязан быть положительным; адаптер не обязан вычислять
        отрицательные/нулевые лимиты — это контракт уровня use-case-а,
        где валидируется DTO.
        """

    @abc.abstractmethod
    async def list_active_for_broadcast(
        self,
        *,
        locale_filter: str,
    ) -> Sequence[BroadcastRecipient]:
        """Список адресатов broadcast-а `/announce` (Спринт 2.5-D.4, ГДД §18.6.5).

        Возвращает только `ACTIVE`-игроков (замороженные / забаненные
        не получают рассылок: первые временно отстранены от игры,
        вторые — навсегда). Сортировка: `id ASC` — стабильный порядок,
        чтобы повторный батч после рестарта (если когда-нибудь
        добавим recovery) шёл в той же последовательности.

        `locale_filter` — фильтр по локали игрока. Поддерживаемые
        значения определены в `application/admin/broadcast_announcement.py`
        (`BroadcastLocaleFilter`):

        * `"ru"` — только игроки с `locale_override = "ru"`. Игроки без
          явного выбора (NULL) **не** включаются: их фактический язык
          резолвится из Telegram-`language_code` в момент сообщения,
          и предсказать его статически нельзя.
        * `"en"` — игроки с `locale_override = "en"` И с `locale_override IS NULL`
          (последние подпадают под `DEFAULT_LOCALE = "en"` —
          см. `application/i18n/locale.py`).
        * `"all"` — все активные игроки, без фильтра по локали.

        `effective_locale` в `BroadcastRecipient` для каждой записи —
        это `locale_override or "en"`, чтобы потребитель не дублировал
        fallback-логику. Возврат — `Sequence` (мы материализуем весь
        список в памяти, потому что для MVP-масштаба `< 50k` игроков
        это безопасно; если когда-нибудь упрёмся — добавим стриминговую
        версию через `AsyncIterator` отдельным методом).
        """
