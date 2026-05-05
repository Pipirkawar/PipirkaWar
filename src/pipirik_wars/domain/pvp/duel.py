"""Агрегат `Duel` — жизненный цикл боя 1×1 (ГДД §7.1, Спринт 2.1.B).

Бой проходит через 4 состояния:

* ``PENDING_ACCEPT`` — вызов создан, ждём `accept` от оппонента
  (или `cancel`, если истёк TTL / бросивший передумал).
* ``IN_PROGRESS``    — оба игрока в бою; на каждом раунде по очереди
  отправляют `submit_move(...)`. Когда оба выбрали — раунд
  автоматически разрешается через `resolve_round`. После
  `expected_rounds` раундов агрегат переходит в `COMPLETED`.
* ``COMPLETED``      — бой разрешён, итоговая `DuelOutcome` посчитана
  через `resolve_duel`. Use-case 2.1.D начислит ±длину игрокам через
  `progression.add_length(source=PVP_REWARD)`.
* ``CANCELLED``      — терминальное (вызов отменён до начала боя).

Архитектурные решения:

* **Снапшот длин на старте** — поля ``p1_initial_length_cm`` /
  ``p2_initial_length_cm`` фиксируются в момент `accept(...)`. Все 3
  раунда используют именно эти значения (path-independent резолв из
  Спринта 2.1.A). Это устойчиво к параллельным `/forest` или другим
  начислениям длины посреди боя — урон считается от стартовой длины.
* **Снапшот баланса на старте** — `hit_pct` и `expected_rounds`
  замораживаются на момент создания вызова. `/balance_reload` посреди
  боя не сбивает экономику текущей дуэли.
* **Иммутабельность** — все мутаторы возвращают новый инстанс через
  `dataclasses.replace`. Старая ссылка остаётся валидной (например,
  для audit-buffer-а).
* **Без `random`** — AFK-фоллбэк (`force_complete_round`) принимает
  `Position`-выборы снаружи; источник случайности (`IRandom`) живёт
  в use-case-е 2.1.E, чтобы домен оставался детерминированным.
* **`challenged_id is None` для `GLOBAL_ONLY`** — в момент создания
  вызова противника ещё нет; он определяется в `accept(...)` (первый,
  кто принял из лобби). Для `CHAT_ONLY` / `CHAT_THEN_GLOBAL` —
  `challenged_id` известен сразу (тот, кого вызвали в чате).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from pipirik_wars.domain.pvp.entities import (
    DuelOutcome,
    RoundChoice,
    RoundOutcome,
)
from pipirik_wars.domain.pvp.errors import (
    InvalidDuelStateError,
    InvalidLengthError,
    MoveAlreadySubmittedError,
    NoMissingMovesError,
    NotADuelParticipantError,
    SelfChallengeError,
)
from pipirik_wars.domain.pvp.services import resolve_duel, resolve_round

__all__ = [
    "Duel",
    "DuelMode",
    "DuelState",
    "PendingRound",
]


class DuelState(StrEnum):
    """Жизненный цикл агрегата `Duel` (ГДД §7.1).

    Граф переходов:

    ``PENDING_ACCEPT`` → ``IN_PROGRESS`` (через `accept`) или
    ``CANCELLED`` (через `cancel` / TTL-истечение).

    ``IN_PROGRESS`` → ``COMPLETED`` (после ``expected_rounds`` раундов).

    ``COMPLETED`` и ``CANCELLED`` — терминальные.
    """

    PENDING_ACCEPT = "pending_accept"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DuelMode(StrEnum):
    """Режим вызова на бой (ГДД §7.1).

    * ``CHAT_THEN_GLOBAL`` — по умолчанию: вызов уходит в чат, через
      3 минуты без `accept`-а — авто-промоут в глобальное лобби (TTL
      10 мин). Логика автопромоута живёт в шедулер-job-е 2.1.D.
    * ``CHAT_ONLY``        — только в чат; авто-промоут отключён.
      По истечении 3 мин вызов отменяется.
    * ``GLOBAL_ONLY``      — сразу в глобальное лобби, минуя чат.
      ``challenged_id`` неизвестен до `accept`-а.
    """

    CHAT_THEN_GLOBAL = "chat_then_global"
    CHAT_ONLY = "chat_only"
    GLOBAL_ONLY = "global_only"


@dataclass(frozen=True, slots=True)
class PendingRound:
    """Раунд в процессе выбора (часть состояния `Duel.IN_PROGRESS`).

    Семантика полей:

    * ``round_num`` — 1-based номер текущего раунда (1..expected_rounds).
    * ``p1_choice`` / ``p2_choice`` — выбор стороны: ``None``, если
      игрок ещё не отправил `submit_move`. Когда оба не-None — раунд
      готов к авторазрешению (`Duel._resolve_pending_round`).
    """

    round_num: int
    p1_choice: RoundChoice | None
    p2_choice: RoundChoice | None

    @property
    def is_complete(self) -> bool:
        """Оба игрока выбрали — раунд готов к разрешению."""

        return self.p1_choice is not None and self.p2_choice is not None

    @property
    def has_any_move(self) -> bool:
        """Хотя бы один игрок выбрал."""

        return self.p1_choice is not None or self.p2_choice is not None


@dataclass(frozen=True, slots=True)
class Duel:
    """Агрегат боя 1×1 (ГДД §7.1).

    Хранит весь жизненный цикл — от создания вызова до итоговой
    `DuelOutcome`. Persistence-слой 2.1.C сериализует поле-в-поле в
    таблицу `pvp_duels` (плюс `pvp_duel_rounds` для `completed_rounds`).
    """

    id: int | None
    challenger_id: int
    challenged_id: int | None
    mode: DuelMode
    state: DuelState
    hit_pct: int
    expected_rounds: int
    created_at: datetime
    accepted_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    p1_initial_length_cm: int | None
    p2_initial_length_cm: int | None
    completed_rounds: tuple[RoundOutcome, ...]
    pending_round: PendingRound | None
    final_outcome: DuelOutcome | None

    # ─── Конструктор ───

    @classmethod
    def create_challenge(
        cls,
        *,
        challenger_id: int,
        challenged_id: int | None,
        mode: DuelMode,
        hit_pct: int,
        expected_rounds: int,
        now: datetime,
    ) -> Duel:
        """Создать новый pending-вызов.

        Для ``CHAT_ONLY`` / ``CHAT_THEN_GLOBAL`` — ``challenged_id``
        обязателен (вызвали конкретного игрока в чате). Для
        ``GLOBAL_ONLY`` — ``None`` (определится при `accept`).

        Бросить вызов самому себе нельзя — `SelfChallengeError`.
        """

        if challenged_id is not None and challenger_id == challenged_id:
            raise SelfChallengeError(player_id=challenger_id)
        if expected_rounds < 1:
            raise ValueError("Duel expected_rounds must be >= 1")
        if not 0 <= hit_pct <= 100:
            raise ValueError("Duel hit_pct must be in [0, 100]")
        if mode is DuelMode.GLOBAL_ONLY and challenged_id is not None:
            raise ValueError(
                "Duel GLOBAL_ONLY mode must not specify challenged_id at creation",
            )
        if mode is not DuelMode.GLOBAL_ONLY and challenged_id is None:
            raise ValueError(
                f"Duel {mode.value} mode requires challenged_id at creation",
            )
        return cls(
            id=None,
            challenger_id=challenger_id,
            challenged_id=challenged_id,
            mode=mode,
            state=DuelState.PENDING_ACCEPT,
            hit_pct=hit_pct,
            expected_rounds=expected_rounds,
            created_at=now,
            accepted_at=None,
            completed_at=None,
            cancelled_at=None,
            p1_initial_length_cm=None,
            p2_initial_length_cm=None,
            completed_rounds=(),
            pending_round=None,
            final_outcome=None,
        )

    # ─── Свойства ───

    @property
    def is_pending(self) -> bool:
        return self.state is DuelState.PENDING_ACCEPT

    @property
    def is_in_progress(self) -> bool:
        return self.state is DuelState.IN_PROGRESS

    @property
    def is_completed(self) -> bool:
        return self.state is DuelState.COMPLETED

    @property
    def is_cancelled(self) -> bool:
        return self.state is DuelState.CANCELLED

    @property
    def is_terminal(self) -> bool:
        """Бой завершён в любом виде (победа/ничья/отмена)."""

        return self.state in (DuelState.COMPLETED, DuelState.CANCELLED)

    def is_participant(self, player_id: int) -> bool:
        """`True`, если `player_id` — одна из сторон боя.

        Для `GLOBAL_ONLY` до `accept`-а `challenged_id is None`,
        и в этом случае только `challenger_id` считается участником.
        """

        return player_id in (self.challenger_id, self.challenged_id)

    # ─── Lifecycle-мутаторы ───

    def accept(
        self,
        *,
        accepter_id: int,
        p1_length_cm: int,
        p2_length_cm: int,
        now: datetime,
    ) -> Duel:
        """Принять вызов и стартовать бой.

        Для `GLOBAL_ONLY` — ``challenged_id`` устанавливается в
        ``accepter_id``. Для остальных режимов — ``accepter_id``
        обязан совпадать с `challenged_id` (нельзя «перехватить»
        чужой вызов).

        Длины игроков снапшотятся в ``p1_initial_length_cm`` /
        ``p2_initial_length_cm`` и используются на всех раундах
        (path-independent резолв).
        """

        if self.state is not DuelState.PENDING_ACCEPT:
            raise InvalidDuelStateError(
                expected=DuelState.PENDING_ACCEPT,
                actual=self.state,
                op="accept",
            )
        if accepter_id == self.challenger_id:
            raise NotADuelParticipantError(player_id=accepter_id)
        if self.challenged_id is not None and accepter_id != self.challenged_id:
            raise NotADuelParticipantError(player_id=accepter_id)
        if p1_length_cm < 0:
            raise InvalidLengthError(side="p1", length_cm=p1_length_cm)
        if p2_length_cm < 0:
            raise InvalidLengthError(side="p2", length_cm=p2_length_cm)
        return replace(
            self,
            challenged_id=accepter_id,
            state=DuelState.IN_PROGRESS,
            accepted_at=now,
            p1_initial_length_cm=p1_length_cm,
            p2_initial_length_cm=p2_length_cm,
            pending_round=PendingRound(
                round_num=1,
                p1_choice=None,
                p2_choice=None,
            ),
        )

    def cancel(self, *, now: datetime) -> Duel:
        """Отменить pending-вызов (TTL истёк / автор передумал).

        Идемпотентен: повторная отмена уже отменённой дуэли — no-op.
        Из других состояний отмена недопустима (бой уже идёт или
        завершён).
        """

        if self.state is DuelState.CANCELLED:
            return self
        if self.state is not DuelState.PENDING_ACCEPT:
            raise InvalidDuelStateError(
                expected=DuelState.PENDING_ACCEPT,
                actual=self.state,
                op="cancel",
            )
        return replace(self, state=DuelState.CANCELLED, cancelled_at=now)

    def submit_move(
        self,
        *,
        player_id: int,
        choice: RoundChoice,
        now: datetime,
    ) -> Duel:
        """Отправить выбор атаки/блока на текущий раунд.

        Если этим вызовом текущий раунд закрылся (оба выбрали) —
        раунд авто-разрешается через `resolve_round`, и:

        * либо стартует следующий раунд (`pending_round.round_num + 1`),
        * либо агрегат переходит в `COMPLETED` (после `expected_rounds`).

        Параметры:

        * ``player_id`` — отправитель. Обязан быть участником боя
          (`challenger_id` или `challenged_id`); иначе
          `NotADuelParticipantError`.
        * ``choice``    — `RoundChoice(attack, block)`. Обе позиции
          обязательны (контракт `RoundChoice` — frozen-датакласс).
        * ``now``       — момент применения (используется при
          переходе в `COMPLETED` для `completed_at`).

        Если игрок уже отправил выбор на этот раунд — повторный
        `submit_move` отклоняется `MoveAlreadySubmittedError`.
        Use-case 2.1.E может вместо обычного отказа подсветить
        пользователю «вы уже выбрали».
        """

        if self.state is not DuelState.IN_PROGRESS:
            raise InvalidDuelStateError(
                expected=DuelState.IN_PROGRESS,
                actual=self.state,
                op="submit_move",
            )
        if not self.is_participant(player_id):
            raise NotADuelParticipantError(player_id=player_id)
        # Инвариант: в IN_PROGRESS pending_round всегда существует
        # (выставлен в `accept` и обновляется в `_resolve_pending_round`).
        pending = self.pending_round
        if pending is None:
            raise InvalidDuelStateError(
                expected=DuelState.IN_PROGRESS,
                actual=self.state,
                op="submit_move",
            )
        side = self._side_for_player(player_id)
        if side == "p1":
            if pending.p1_choice is not None:
                raise MoveAlreadySubmittedError(
                    player_id=player_id,
                    round_num=pending.round_num,
                )
            new_pending = replace(pending, p1_choice=choice)
        else:  # side == "p2"
            if pending.p2_choice is not None:
                raise MoveAlreadySubmittedError(
                    player_id=player_id,
                    round_num=pending.round_num,
                )
            new_pending = replace(pending, p2_choice=choice)
        if not new_pending.is_complete:
            return replace(self, pending_round=new_pending)
        return self._resolve_pending_round(pending=new_pending, now=now)

    def force_complete_round(
        self,
        *,
        p1_fallback: RoundChoice | None,
        p2_fallback: RoundChoice | None,
        now: datetime,
    ) -> Duel:
        """AFK-фоллбэк: подставить случайные выборы тем, кто не выбрал.

        Use-case 2.1.E вызывает этот метод, когда раунд-таймер истёк
        и хотя бы один игрок не отправил `submit_move`. Для каждого
        такого игрока use-case заранее берёт случайный `Position`
        через `IRandom` и собирает `RoundChoice(attack, block)` —
        результат передаётся сюда.

        Контракт: ``X_fallback`` ОБЯЗАН быть `None`, если игрок уже
        выбрал (защита от двойного применения), и `RoundChoice`,
        если выбора ещё нет. Если оба игрока уже выбрали — ничего
        не делать незачем; вызов `NoMissingMovesError`.
        """

        if self.state is not DuelState.IN_PROGRESS:
            raise InvalidDuelStateError(
                expected=DuelState.IN_PROGRESS,
                actual=self.state,
                op="force_complete_round",
            )
        pending = self.pending_round
        if pending is None:
            raise InvalidDuelStateError(
                expected=DuelState.IN_PROGRESS,
                actual=self.state,
                op="force_complete_round",
            )
        if pending.is_complete:
            raise NoMissingMovesError(round_num=pending.round_num)
        new_p1 = pending.p1_choice
        new_p2 = pending.p2_choice
        if new_p1 is None:
            if p1_fallback is None:
                raise NoMissingMovesError(round_num=pending.round_num)
            new_p1 = p1_fallback
        elif p1_fallback is not None:
            raise MoveAlreadySubmittedError(
                player_id=self.challenger_id,
                round_num=pending.round_num,
            )
        if new_p2 is None:
            if p2_fallback is None:
                raise NoMissingMovesError(round_num=pending.round_num)
            new_p2 = p2_fallback
        elif p2_fallback is not None:
            # challenged_id is set in IN_PROGRESS (validated by `accept`).
            assert self.challenged_id is not None
            raise MoveAlreadySubmittedError(
                player_id=self.challenged_id,
                round_num=pending.round_num,
            )
        new_pending = PendingRound(
            round_num=pending.round_num,
            p1_choice=new_p1,
            p2_choice=new_p2,
        )
        return self._resolve_pending_round(pending=new_pending, now=now)

    # ─── Внутренние помощники ───

    def _side_for_player(self, player_id: int) -> str:
        if player_id == self.challenger_id:
            return "p1"
        if player_id == self.challenged_id:
            return "p2"
        raise NotADuelParticipantError(player_id=player_id)

    def _resolve_pending_round(self, *, pending: PendingRound, now: datetime) -> Duel:
        # Инварианты вызывающего кода: оба выбора заданы, длины снэпшоты
        # выставлены в `accept`-е.
        assert pending.p1_choice is not None
        assert pending.p2_choice is not None
        assert self.p1_initial_length_cm is not None
        assert self.p2_initial_length_cm is not None
        outcome = resolve_round(
            p1=pending.p1_choice,
            p2=pending.p2_choice,
            p1_length_cm=self.p1_initial_length_cm,
            p2_length_cm=self.p2_initial_length_cm,
            hit_pct=self.hit_pct,
        )
        new_completed = (*self.completed_rounds, outcome)
        if len(new_completed) >= self.expected_rounds:
            duel_outcome = resolve_duel(
                rounds=tuple((r.p1_choice, r.p2_choice) for r in new_completed),
                p1_length_cm=self.p1_initial_length_cm,
                p2_length_cm=self.p2_initial_length_cm,
                hit_pct=self.hit_pct,
                expected_rounds=self.expected_rounds,
            )
            return replace(
                self,
                state=DuelState.COMPLETED,
                completed_at=now,
                completed_rounds=new_completed,
                pending_round=None,
                final_outcome=duel_outcome,
            )
        return replace(
            self,
            completed_rounds=new_completed,
            pending_round=PendingRound(
                round_num=len(new_completed) + 1,
                p1_choice=None,
                p2_choice=None,
            ),
        )
