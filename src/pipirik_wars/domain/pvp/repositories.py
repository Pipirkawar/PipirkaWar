"""Порты репозиториев PvP-подсистемы (Спринт 2.1.C, расширено в 2.2.D).

`IDuelRepository` — доступ к таблице `pvp_duels` (+ `pvp_duel_rounds`
для completed-раундов). Сериализует поле-в-поле агрегат `Duel`
из домена 2.1.B.

`IMassDuelRepository` (Спринт 2.2.D) — доступ к таблицам
`pvp_mass_duels` (+ `pvp_mass_duel_choices` для ростера/выборов +
`pvp_mass_duel_damage_entries` для completed-исхода). Сериализует
поле-в-поле агрегат `MassDuel` из домена 2.2.C.

Все методы исполняются внутри активного `IUnitOfWork`; собственный
коммит репозиторий не делает (правило Спринта 0.2). Use-case-ы 2.1.D
/ 2.2.E вызывают `add(...)` / `save(...)` через ambient-UoW.
"""

from __future__ import annotations

import abc

from pipirik_wars.domain.pvp.duel import Duel
from pipirik_wars.domain.pvp.mass_duel import MassDuel


class IDuelRepository(abc.ABC):
    """Доступ к таблице `pvp_duels` (через `pvp_duel_rounds` для completed-раундов)."""

    @abc.abstractmethod
    async def add(self, duel: Duel) -> Duel:
        """Добавить новый duel-агрегат.

        На вход — `duel.id is None`. Возвращает копию с проставленным
        `id` (PK из БД). Завершённые раунды (`completed_rounds`)
        записываются в `pvp_duel_rounds` через тот же `INSERT`.

        Бросает доменный `IntegrityError`, если БД-уровневые
        CHECK-/FK-инварианты нарушены (например, `challenger_id` не
        существует в `users`).
        """

    @abc.abstractmethod
    async def get_by_id(self, *, duel_id: int) -> Duel | None:
        """Найти duel по `id`, либо `None`.

        Загружает root-row из `pvp_duels` и все связанные
        completed-раунды из `pvp_duel_rounds` (в порядке `round_num`).
        """

    @abc.abstractmethod
    async def save(self, duel: Duel) -> Duel:
        """Обновить существующий duel-агрегат по `id`.

        На вход — `duel.id is not None`. Перезаписывает все поля
        root-row-а и синхронизирует `pvp_duel_rounds` (новые
        completed-раунды добавляются; уже существующие не трогаются —
        в домене round-record иммутабелен после авторазрешения).

        Бросает доменный `IntegrityError`, если запись с таким `id` не
        найдена или БД-уровневые инварианты нарушены.
        """


class IMassDuelRepository(abc.ABC):
    """Доступ к `pvp_mass_duels` (+ `pvp_mass_duel_choices` для ростера +
    `pvp_mass_duel_damage_entries` для итогового outcome).

    Сериализация агрегата :class:`MassDuel` (домен 2.2.C):

    * root-row → `pvp_mass_duels`: `clan{1,2}_id`, `state`, `hit_pct`,
      `created_at` / `completed_at` / `cancelled_at`, финальные
      `final_clan{1,2}_total_dealt` / `final_clan{1,2}_delta_cm` /
      `final_winner` (nullable, заполняются только при `COMPLETED`).
    * `clan{1,2}_member_ids` × `clan{1,2}_initial_lengths` ×
      `clan{1,2}_choices` → `pvp_mass_duel_choices` (1:N от root-а):
      одна строка на каждого участника, поля `attack`/`block`/
      `submitted_at` nullable до `submit_move`-а, `clan_side` хранит
      принадлежность к ростеру (clan1/clan2), `initial_length_cm` —
      снапшот.
    * `final_outcome.outcome.damage_entries` → `pvp_mass_duel_damage_entries`
      (1:N от root-а, только для COMPLETED-боёв): один row на каждый
      разрешённый удар (с порядком `entry_idx`, повторяющим порядок
      из `mass_services.resolve_mass_duel`).
    """

    @abc.abstractmethod
    async def add(self, duel: MassDuel) -> MassDuel:
        """Добавить новый mass-duel-агрегат.

        На вход — `duel.id is None`. Возвращает копию с проставленным
        `id` (PK из БД). Все участники (clan1+clan2) сразу пишутся в
        `pvp_mass_duel_choices` со снапшотами длин и (если на момент
        `add` уже был `submit_move`) с уже сохранёнными выборами.

        Бросает доменный `IntegrityError`, если БД-уровневые
        CHECK-/FK-инварианты нарушены (например, `clan1_id` или
        `player_id` не существует в соответствующих таблицах).
        """

    @abc.abstractmethod
    async def get_by_id(self, *, duel_id: int) -> MassDuel | None:
        """Найти mass-duel по `id`, либо `None`.

        Загружает root-row из `pvp_mass_duels`, все участников из
        `pvp_mass_duel_choices` (отсортированных по `(clan_side, player_id)`
        для детерминированного восстановления параллельных tuple-ов
        агрегата) и — для COMPLETED-боёв — все damage-entries из
        `pvp_mass_duel_damage_entries` (по `entry_idx ASC`).
        """

    @abc.abstractmethod
    async def save(self, duel: MassDuel) -> MassDuel:
        """Обновить существующий mass-duel-агрегат по `id`.

        На вход — `duel.id is not None`. Перезаписывает все поля
        root-row-а, синхронизирует `pvp_mass_duel_choices` (UPDATE
        существующих по PK `(duel_id, player_id)` — выборы могут
        переходить из `NULL` в заполненные, обратное не допускается
        доменом) и при `state == COMPLETED` сохраняет
        `final_outcome.outcome.damage_entries` в
        `pvp_mass_duel_damage_entries` (если ещё не были записаны;
        damage-entries иммутабельны после `resolve(...)`).

        Бросает доменный `IntegrityError`, если запись с таким `id` не
        найдена, ростер несовместим (нельзя удалять/добавлять
        участников после `add(...)`) или БД-уровневые инварианты
        нарушены.
        """

    @abc.abstractmethod
    async def find_most_recent_for_clan(self, *, clan_id: int) -> MassDuel | None:
        """Найти самый свежий mass-duel для указанного клана (любая сторона).

        Используется в use-case `StartMassDuel` (Спринт 2.2.E) для
        проверки cooldown-а 6 часов (ГДД §7.2 / 2.2.2): если у клана
        был mass-duel за последние `pvp.mass_duel.cooldown_hours` —
        отказ в новой атаке.

        Контракт реализаций:
        - возвращает запись с максимальным `created_at` среди всех
          mass-duel-ов, где `clan{1,2}_id == clan_id` (любая роль —
          атакующий или защитник);
        - сортирует по `created_at DESC, id DESC` для детерминизма
          при совпадающих timestamp-ах;
        - возвращает `None`, если у клана нет ни одного mass-duel-а
          (включая отменённые/завершённые — cooldown тикается с
          момента старта боя независимо от исхода).
        """
