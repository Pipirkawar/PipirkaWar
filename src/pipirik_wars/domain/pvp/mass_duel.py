"""Агрегат `MassDuel` — жизненный цикл массового PvP-боя клан×клан (ГДД §7.2,
Спринт 2.2.C).

Бой проходит через 3 состояния:

* ``IN_PROGRESS`` — бой стартовал; ростеры обоих кланов и снапшоты длин
  заморожены. Каждый участник отправляет ``submit_move`` ровно один раз.
* ``COMPLETED``   — все участники отправили (или AFK-фоллбэк через
  ``force_submit_missing``), `resolve(...)` посчитал
  :class:`MassDuelOutcome`. Терминальное.
* ``CANCELLED``   — бой отменён до резолва (например, ростер кланов
  деградировал из-за отписок, или админский abort). Терминальное.

Ключевые отличия от 1×1-агрегата :class:`Duel`:

* **Нет `PENDING_ACCEPT`** — массовый бой не требует «принятия» вызова
  оппонентом. Use-case 2.2.D автоматически записывает всех eligible
  участников обоих кланов (длина ≥ `min_length_cm`, толщина ≥
  `min_thickness_level`) и переходит сразу в ``IN_PROGRESS``.
* **Нет раундов** — бой одно-тиковый (ГДД §7.2 / 2.2.4). Каждый
  участник заявляет одну атаку и один блок, всё разрешается за
  один `resolve(...)`-вызов.
* **N×M участников** — на каждой стороне 1..N игроков. Внутри
  агрегата — параллельные кортежи `clan{1,2}_member_ids`,
  `clan{1,2}_initial_lengths`, `clan{1,2}_choices` (`None` пока
  игрок не отправил). Сортировка по `member_id` — для
  детерминированного хэширования и стабильного persistence-mapping-а.

Архитектурные решения:

* **Снапшот длин на старте** — `clan{1,2}_initial_lengths` фиксируются
  в `create_battle(...)`. `resolve(...)` считает урон именно от этих
  значений (path-independent), не от текущего `Player.length_cm`.
  Параллельные `/forest` или другие начисления длины посреди боя не
  влияют на исход.
* **Снапшот баланса на старте** — `hit_pct` замораживается на момент
  создания. `/balance_reload` посреди боя не сбивает экономику текущего
  массового боя (симметрично 1×1-Duel-у).
* **Иммутабельность** — все мутаторы возвращают новый инстанс через
  ``dataclasses.replace`` + переписку `tuple`-полей. Старая ссылка
  остаётся валидной.
* **Без `random`** — `resolve(...)` принимает :class:`IRandom` извне
  (нужен `pair_attackers` внутри `resolve_mass_duel`). AFK-фоллбэк
  (`force_submit_missing`) принимает уже посчитанный
  ``Mapping[player_id, MassRoundChoice]`` снаружи; сам выбор
  random-position-ов делает use-case 2.2.E.
* **`cancel` идемпотентен** — повторная отмена уже отменённого боя
  возвращает self без перевода состояния. Из ``COMPLETED`` отмена
  запрещена (бой уже завершён, его нельзя «откатить»).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from pipirik_wars.domain.pvp.errors import (
    InvalidMassDuelStateError,
    MassDuelNotReadyError,
    MassMoveAlreadySubmittedError,
    NoMissingMassMovesError,
    NotAMassDuelParticipantError,
)
from pipirik_wars.domain.pvp.mass import (
    MassDuelOutcome,
    MassRoundChoice,
)
from pipirik_wars.domain.pvp.mass_services import resolve_mass_duel
from pipirik_wars.domain.shared.ports.random import IRandom

__all__ = [
    "MassDuel",
    "MassDuelState",
]


class MassDuelState(StrEnum):
    """Жизненный цикл агрегата :class:`MassDuel` (ГДД §7.2).

    Граф переходов:

    ``IN_PROGRESS`` → ``COMPLETED`` (через `resolve(...)` после того,
    как все участники отправили выборы).

    ``IN_PROGRESS`` → ``CANCELLED`` (через `cancel(...)` — например, при
    деградации ростера или админ-вмешательстве).

    ``COMPLETED`` и ``CANCELLED`` — терминальные.

    Состояния `PENDING_ACCEPT` нет (в отличие от 1×1-боя): массовый бой
    не требует подтверждения оппонентом, обе стороны автозаписываются
    use-case-ом 2.2.D и сразу стартуют.
    """

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class MassDuel:
    """Агрегат массового PvP-боя клан×клан (ГДД §7.2).

    Хранит весь жизненный цикл — от создания (с зафиксированным
    ростером) до итоговой :class:`MassDuelOutcome`. Persistence-слой
    2.2.D сериализует поле-в-поле в таблицу `pvp_mass_duels` (плюс
    `pvp_mass_duel_choices` для choices и `pvp_mass_duel_damage_entries`
    для outcome).

    Соглашения по форматам полей:

    * `clan{1,2}_member_ids`        — отсортированный по возрастанию
      кортеж уникальных `player_id` (отсортировано в `create_battle`).
    * `clan{1,2}_initial_lengths`   — кортеж длин той же длины и в том
      же порядке, что `clan{1,2}_member_ids`.
      `clan1_initial_lengths[i]` == длина `clan1_member_ids[i]`.
    * `clan{1,2}_choices`           — кортеж той же длины:
      ``None`` означает «игрок ещё не отправил выбор», иначе
      :class:`MassRoundChoice` с `player_id == clan{1,2}_member_ids[i]`.
    """

    id: int | None
    clan1_id: int
    clan2_id: int
    state: MassDuelState
    hit_pct: int
    clan1_member_ids: tuple[int, ...]
    clan2_member_ids: tuple[int, ...]
    clan1_initial_lengths: tuple[int, ...]
    clan2_initial_lengths: tuple[int, ...]
    clan1_choices: tuple[MassRoundChoice | None, ...]
    clan2_choices: tuple[MassRoundChoice | None, ...]
    created_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    final_outcome: MassDuelOutcome | None

    def _validate_terminal_state_invariants(self) -> None:
        """Связывает `state` с полями `final_outcome`/`completed_at`/`cancelled_at`."""

        if self.state is MassDuelState.COMPLETED:
            if self.final_outcome is None:
                raise ValueError("COMPLETED mass-duel must have final_outcome")
            if self.completed_at is None:
                raise ValueError("COMPLETED mass-duel must have completed_at")
        elif self.final_outcome is not None:
            raise ValueError(
                f"non-COMPLETED mass-duel must not have final_outcome, state={self.state}"
            )
        if self.state is MassDuelState.CANCELLED and self.cancelled_at is None:
            raise ValueError("CANCELLED mass-duel must have cancelled_at")

    def __post_init__(self) -> None:
        # Базовые инварианты, проверяемые независимо от того, как был
        # сконструирован агрегат (через `create_battle` или после
        # десериализации из БД в use-case 2.2.D).
        if self.clan1_id <= 0:
            raise ValueError(f"clan1_id must be > 0, got {self.clan1_id}")
        if self.clan2_id <= 0:
            raise ValueError(f"clan2_id must be > 0, got {self.clan2_id}")
        if self.clan1_id == self.clan2_id:
            raise ValueError(f"clan1_id and clan2_id must differ, got {self.clan1_id}")
        if not 0 <= self.hit_pct <= 100:
            raise ValueError(f"hit_pct must be in [0, 100], got {self.hit_pct}")
        if not self.clan1_member_ids:
            raise ValueError("clan1_member_ids must be non-empty")
        if not self.clan2_member_ids:
            raise ValueError("clan2_member_ids must be non-empty")
        _check_member_ids(side="clan1", member_ids=self.clan1_member_ids)
        _check_member_ids(side="clan2", member_ids=self.clan2_member_ids)
        # Ростеры разных кланов не должны пересекаться: ГДД §7.2 / 2.2.3
        # «игрок в обоих кланах — пропускается». Use-case 2.2.D
        # дедуплицирует ростер ДО `create_battle`.
        overlap = set(self.clan1_member_ids) & set(self.clan2_member_ids)
        if overlap:
            raise ValueError(f"clan rosters must be disjoint, got overlap: {sorted(overlap)}")
        _check_parallel_lengths(
            side="clan1",
            member_ids=self.clan1_member_ids,
            lengths=self.clan1_initial_lengths,
        )
        _check_parallel_lengths(
            side="clan2",
            member_ids=self.clan2_member_ids,
            lengths=self.clan2_initial_lengths,
        )
        _check_parallel_choices(
            side="clan1",
            member_ids=self.clan1_member_ids,
            choices=self.clan1_choices,
        )
        _check_parallel_choices(
            side="clan2",
            member_ids=self.clan2_member_ids,
            choices=self.clan2_choices,
        )
        # Состояние COMPLETED ⇒ final_outcome != None и completed_at != None.
        self._validate_terminal_state_invariants()

    # ─── Конструктор ───

    @classmethod
    def create_battle(
        cls,
        *,
        clan1_id: int,
        clan2_id: int,
        clan1_lengths: Mapping[int, int],
        clan2_lengths: Mapping[int, int],
        hit_pct: int,
        now: datetime,
    ) -> MassDuel:
        """Создать новый массовый бой и сразу перейти в `IN_PROGRESS`.

        Аргументы:

        * `clan1_id` / `clan2_id` — ID кланов, должны быть разными
          положительными числами.
        * `clan{1,2}_lengths`    — словарь `player_id → length_cm`
          для каждого участника соответствующего клана. Все ключи > 0,
          все значения ≥ 0, словари непустые.
        * `hit_pct`              — балансовый % урона, snapshot-ится на
          старте боя; `[0..100]`.
        * `now`                  — момент создания.

        Конструктор:

        1. Валидирует входы (см. `__post_init__` — там же повторно).
        2. Сортирует ростеры по `player_id` для детерминированности.
        3. Возвращает свежесозданный агрегат в `IN_PROGRESS` со всеми
           `clan{1,2}_choices = (None, None, ...)` (никто ещё не
           отправил выбор).
        """

        # Защита от пересечения ростеров — выбрасывается также в
        # `__post_init__`, но даём раннее, более информативное сообщение.
        clan1_set = set(clan1_lengths)
        clan2_set = set(clan2_lengths)
        overlap = clan1_set & clan2_set
        if overlap:
            raise ValueError(f"clan rosters must be disjoint, got overlap: {sorted(overlap)}")

        clan1_ids = tuple(sorted(clan1_lengths))
        clan2_ids = tuple(sorted(clan2_lengths))
        clan1_lens = tuple(clan1_lengths[pid] for pid in clan1_ids)
        clan2_lens = tuple(clan2_lengths[pid] for pid in clan2_ids)
        return cls(
            id=None,
            clan1_id=clan1_id,
            clan2_id=clan2_id,
            state=MassDuelState.IN_PROGRESS,
            hit_pct=hit_pct,
            clan1_member_ids=clan1_ids,
            clan2_member_ids=clan2_ids,
            clan1_initial_lengths=clan1_lens,
            clan2_initial_lengths=clan2_lens,
            clan1_choices=tuple([None] * len(clan1_ids)),
            clan2_choices=tuple([None] * len(clan2_ids)),
            created_at=now,
            completed_at=None,
            cancelled_at=None,
            final_outcome=None,
        )

    # ─── Свойства ───

    @property
    def is_in_progress(self) -> bool:
        return self.state is MassDuelState.IN_PROGRESS

    @property
    def is_completed(self) -> bool:
        return self.state is MassDuelState.COMPLETED

    @property
    def is_cancelled(self) -> bool:
        return self.state is MassDuelState.CANCELLED

    @property
    def is_terminal(self) -> bool:
        """Бой завершён (победа/ничья/отмена) — никаких мутаторов больше."""

        return self.state in (MassDuelState.COMPLETED, MassDuelState.CANCELLED)

    @property
    def is_ready_to_resolve(self) -> bool:
        """Все участники отправили выбор — можно звать `resolve(...)`.

        Для боя в состоянии не-`IN_PROGRESS` — возвращает `False`
        (бой уже завершён или отменён).
        """

        if self.state is not MassDuelState.IN_PROGRESS:
            return False
        return all(c is not None for c in self.clan1_choices) and all(
            c is not None for c in self.clan2_choices
        )

    @property
    def missing_player_ids(self) -> tuple[int, ...]:
        """Кортеж `player_id` всех ещё-не-отправивших участников.

        Сортировка совпадает с обходом `clan1` затем `clan2` по
        возрастанию `player_id`.
        """

        out: list[int] = []
        for pid, c in zip(self.clan1_member_ids, self.clan1_choices, strict=True):
            if c is None:
                out.append(pid)
        for pid, c in zip(self.clan2_member_ids, self.clan2_choices, strict=True):
            if c is None:
                out.append(pid)
        return tuple(out)

    def is_participant(self, player_id: int) -> bool:
        """`True`, если `player_id` входит в один из ростеров боя."""

        return player_id in self.clan1_member_ids or player_id in self.clan2_member_ids

    # ─── Lifecycle-мутаторы ───

    def submit_move(
        self,
        *,
        player_id: int,
        choice: MassRoundChoice,
        now: datetime,
    ) -> MassDuel:
        """Зафиксировать выбор одного участника на текущий бой.

        Параметр `now` зарезервирован под будущий аудит-таймстемп
        (домен сейчас не хранит время каждого `submit_move` — оно
        живёт в `audit_log`). Сейчас используется только для проверки
        состояния.

        Ошибки:

        * `InvalidMassDuelStateError` — бой не в `IN_PROGRESS`.
        * `NotAMassDuelParticipantError` — `player_id` не из ростера.
        * `MassMoveAlreadySubmittedError` — повторный `submit_move`
          для уже отправившего игрока.
        * `ValueError` — `choice.player_id != player_id` (выбор
          сделан от чужого имени).
        """

        del now  # unused, см. docstring
        if self.state is not MassDuelState.IN_PROGRESS:
            raise InvalidMassDuelStateError(
                expected=MassDuelState.IN_PROGRESS,
                actual=self.state,
                op="submit_move",
            )
        if choice.player_id != player_id:
            raise ValueError(
                f"choice.player_id={choice.player_id} must match submit_move(player_id={player_id})"
            )
        if not self.is_participant(player_id):
            raise NotAMassDuelParticipantError(player_id=player_id)
        if player_id in self.clan1_member_ids:
            idx = self.clan1_member_ids.index(player_id)
            if self.clan1_choices[idx] is not None:
                raise MassMoveAlreadySubmittedError(player_id=player_id)
            new_clan1 = _replace_at(self.clan1_choices, idx, choice)
            return replace(self, clan1_choices=new_clan1)
        # Иначе игрок в clan2 (точно — мы прошли is_participant).
        idx = self.clan2_member_ids.index(player_id)
        if self.clan2_choices[idx] is not None:
            raise MassMoveAlreadySubmittedError(player_id=player_id)
        new_clan2 = _replace_at(self.clan2_choices, idx, choice)
        return replace(self, clan2_choices=new_clan2)

    def force_submit_missing(
        self,
        *,
        fallback_choices: Mapping[int, MassRoundChoice],
        now: datetime,
    ) -> MassDuel:
        """Заполнить выборы за всех ещё-не-отправивших участников.

        AFK-фоллбэк: use-case 2.2.E собирает рандомные `MassRoundChoice`
        для каждого `missing_player_ids` (через :class:`IRandom`) и
        передаёт сюда. Мутатор:

        * требует `state == IN_PROGRESS`;
        * требует, чтобы хотя бы один игрок был в `missing_player_ids`
          (иначе `NoMissingMassMovesError` — это сигнал баг-в-таймере);
        * требует, чтобы `fallback_choices` покрывали РОВНО
          `missing_player_ids` (без лишних, без пропусков);
        * валидирует, что для каждого `pid` `fallback_choices[pid].player_id == pid`.

        Возвращает новый агрегат с уже заполненными `clan{1,2}_choices`.
        Само разрешение боя — отдельный `resolve(...)`-вызов после этого.

        Параметр `now` зарезервирован под audit-таймстемп.
        """

        del now  # unused, см. docstring
        if self.state is not MassDuelState.IN_PROGRESS:
            raise InvalidMassDuelStateError(
                expected=MassDuelState.IN_PROGRESS,
                actual=self.state,
                op="force_submit_missing",
            )
        missing = self.missing_player_ids
        if not missing:
            raise NoMissingMassMovesError()
        if set(fallback_choices) != set(missing):
            raise ValueError(
                f"fallback_choices keys {sorted(fallback_choices)} "
                f"must equal missing player_ids {sorted(missing)}"
            )
        for pid, ch in fallback_choices.items():
            if ch.player_id != pid:
                raise ValueError(
                    f"fallback_choices[{pid}].player_id={ch.player_id} must match key {pid}"
                )

        new_clan1 = _fill_missing(
            member_ids=self.clan1_member_ids,
            choices=self.clan1_choices,
            fallback=fallback_choices,
        )
        new_clan2 = _fill_missing(
            member_ids=self.clan2_member_ids,
            choices=self.clan2_choices,
            fallback=fallback_choices,
        )
        return replace(self, clan1_choices=new_clan1, clan2_choices=new_clan2)

    def resolve(
        self,
        *,
        random: IRandom,
        now: datetime,
    ) -> MassDuel:
        """Разрешить массовый бой — посчитать :class:`MassDuelOutcome`.

        Требования:

        * `state == IN_PROGRESS`;
        * все участники отправили выбор (`is_ready_to_resolve == True`).
          Иначе use-case обязан сначала вызвать
          `force_submit_missing(...)`.

        Алгоритм:

        1. Извлекает уже-не-`None` `clan{1,2}_choices` (через `is_ready_to_resolve`
           гарантировано, что все элементы заполнены).
        2. Вызывает чистую функцию :func:`resolve_mass_duel` (Спринт
           2.2.B) — pairing → matrix → zero-sum дельты → winner.
        3. Возвращает новый агрегат в `COMPLETED` с
           `final_outcome=outcome` и `completed_at=now`.
        """

        if self.state is not MassDuelState.IN_PROGRESS:
            raise InvalidMassDuelStateError(
                expected=MassDuelState.IN_PROGRESS,
                actual=self.state,
                op="resolve",
            )
        missing = self.missing_player_ids
        if missing:
            raise MassDuelNotReadyError(missing_count=len(missing))

        # Гарантировано: все элементы — не None.
        clan1_choices = tuple(c for c in self.clan1_choices if c is not None)
        clan2_choices = tuple(c for c in self.clan2_choices if c is not None)
        clan1_lengths_map = dict(
            zip(self.clan1_member_ids, self.clan1_initial_lengths, strict=True)
        )
        clan2_lengths_map = dict(
            zip(self.clan2_member_ids, self.clan2_initial_lengths, strict=True)
        )
        outcome = resolve_mass_duel(
            clan1_choices=clan1_choices,
            clan2_choices=clan2_choices,
            clan1_initial_lengths=clan1_lengths_map,
            clan2_initial_lengths=clan2_lengths_map,
            hit_pct=self.hit_pct,
            random=random,
        )
        return replace(
            self,
            state=MassDuelState.COMPLETED,
            completed_at=now,
            final_outcome=outcome,
        )

    def cancel(self, *, now: datetime) -> MassDuel:
        """Отменить бой (`IN_PROGRESS → CANCELLED`).

        Идемпотентно: повторная отмена уже отменённого боя возвращает
        self. Из `COMPLETED` отменить нельзя — бой уже завершён,
        откатить нельзя (награды могли быть начислены use-case-ом).
        """

        if self.state is MassDuelState.CANCELLED:
            return self
        if self.state is not MassDuelState.IN_PROGRESS:
            raise InvalidMassDuelStateError(
                expected=MassDuelState.IN_PROGRESS,
                actual=self.state,
                op="cancel",
            )
        return replace(self, state=MassDuelState.CANCELLED, cancelled_at=now)


# ─── Внутренние helper-ы валидации/мутаций ───


def _check_member_ids(*, side: str, member_ids: Sequence[int]) -> None:
    """Гарантирует, что `member_ids` — отсортированный кортеж уникальных >0."""

    seen: set[int] = set()
    prev: int | None = None
    for pid in member_ids:
        if pid <= 0:
            raise ValueError(f"{side}_member_ids: id must be > 0, got {pid}")
        if pid in seen:
            raise ValueError(f"{side}_member_ids: duplicate id {pid}")
        if prev is not None and pid <= prev:
            raise ValueError(f"{side}_member_ids must be sorted ascending, got {prev} before {pid}")
        seen.add(pid)
        prev = pid


def _check_parallel_lengths(
    *,
    side: str,
    member_ids: Sequence[int],
    lengths: Sequence[int],
) -> None:
    if len(lengths) != len(member_ids):
        raise ValueError(
            f"{side}_initial_lengths length {len(lengths)} "
            f"must equal {side}_member_ids length {len(member_ids)}"
        )
    for pid, length_cm in zip(member_ids, lengths, strict=True):
        if length_cm < 0:
            raise ValueError(f"{side}_initial_lengths[{pid}]={length_cm} must be >= 0")


def _check_parallel_choices(
    *,
    side: str,
    member_ids: Sequence[int],
    choices: Sequence[MassRoundChoice | None],
) -> None:
    if len(choices) != len(member_ids):
        raise ValueError(
            f"{side}_choices length {len(choices)} "
            f"must equal {side}_member_ids length {len(member_ids)}"
        )
    for pid, ch in zip(member_ids, choices, strict=True):
        if ch is not None and ch.player_id != pid:
            raise ValueError(
                f"{side}_choices[{pid}].player_id={ch.player_id} must match member_id {pid}"
            )


def _replace_at(
    items: tuple[MassRoundChoice | None, ...],
    idx: int,
    value: MassRoundChoice,
) -> tuple[MassRoundChoice | None, ...]:
    """Иммутабельная замена элемента кортежа по индексу."""

    return (*items[:idx], value, *items[idx + 1 :])


def _fill_missing(
    *,
    member_ids: Sequence[int],
    choices: Sequence[MassRoundChoice | None],
    fallback: Mapping[int, MassRoundChoice],
) -> tuple[MassRoundChoice | None, ...]:
    """Подставить `fallback[pid]` на места, где `choices[i] is None`."""

    out: list[MassRoundChoice | None] = []
    for pid, ch in zip(member_ids, choices, strict=True):
        if ch is None and pid in fallback:
            out.append(fallback[pid])
        else:
            out.append(ch)
    return tuple(out)
