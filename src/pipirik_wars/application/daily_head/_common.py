"""Общая логика обоих триггеров «Главы клана дня» (Спринт 2.3.C).

`_resolve_or_create_assignment(...)` — внутри активного UoW:

1. Зовёт `DailyHeadService.assign_or_get(...)` (preflight + выбор
   кандидата). Если уже назначен (`assignment.id is not None`) —
   читает игрока и возвращает с `was_new=False`.
2. Иначе пытается вставить запись через `heads.add(...)`. На race
   (UNIQUE-violation) перечитывает запись победителя и возвращает
   с `was_new=False` (длина уже начислена выигравшей транзакцией —
   повторно не делаем).
3. На happy-path: `length_granter.grant(...)` (через anti-cheat
   clamp + audit `LENGTH_GRANT`) + `audit.record(DAILY_HEAD_ASSIGN)` +
   re-fetch игрока с применённой прибавкой.

Возвращает `DailyHeadResolved` для UI handler-а.
"""

from __future__ import annotations

from pipirik_wars.application.daily_head.dto import DailyHeadResolved
from pipirik_wars.domain.daily_head import (
    DailyHeadAlreadyAssignedError,
    DailyHeadService,
    DailyHeadSource,
    IDailyHeadRepository,
)
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.shared.ports import IClock
from pipirik_wars.domain.shared.ports.audit import (
    AuditAction,
    AuditEntry,
    AuditSource,
    IAuditLogger,
)


async def _resolve_or_create_assignment(
    *,
    clan_id: int,
    source: DailyHeadSource,
    actor_tg_id: int | None,
    daily_head_service: DailyHeadService,
    heads: IDailyHeadRepository,
    players: IPlayerRepository,
    length_granter: ILengthGranter,
    audit: IAuditLogger,
    clock: IClock,
) -> DailyHeadResolved:
    """Идемпотентно получить или назначить главу клана дня.

    Должен вызываться внутри активного `IUnitOfWork`. Вызывающий код
    отвечает за резолв `clan_id` (по `chat_id` для button-триггера или
    напрямую из cron-аргумента).
    """
    moscow_date = clock.moscow_date()
    assignment = await daily_head_service.assign_or_get(
        clan_id=clan_id,
        source=source,
    )

    # Уже был назначен в эти сутки — идемпотентный возврат.
    if assignment.id is not None:
        player = await players.get_by_id(player_id=assignment.player_id)
        return DailyHeadResolved(
            assignment=assignment,
            player=player,
            was_new=False,
        )

    # Новая запись — пробуем вставить. На race UNIQUE-индекс ловит
    # дубль; конвертируем в идемпотентный возврат записи победителя.
    try:
        saved = await heads.add(assignment)
    except DailyHeadAlreadyAssignedError:
        winner = await heads.get_by_clan_and_date(
            clan_id=clan_id,
            moscow_date=moscow_date,
        )
        # Контракт UNIQUE+repo гарантирует, что после IntegrityError
        # запись существует. None здесь означал бы баг репозитория,
        # лучше прокинуть AssertionError, чем тихо вернуть мусор.
        assert winner is not None
        winner_player = await players.get_by_id(player_id=winner.player_id)
        return DailyHeadResolved(
            assignment=winner,
            player=winner_player,
            was_new=False,
        )

    # Happy-path: прибавка длины через единый ILengthGranter.
    # Anti-cheat clamp + audit LENGTH_GRANT — внутри grant().
    # Idempotency-key стабилен по `(clan_id, moscow_date)` — при ретрае
    # в тех же сутках LENGTH_GRANT-дубликат не возникнет.
    await length_granter.grant(
        player_id=saved.player_id,
        delta_cm=saved.bonus_cm,
        source=AuditSource.DAILY_HEAD,
        reason="daily_head",
        idempotency_key=f"add_length:daily_head:{clan_id}:{moscow_date.isoformat()}",
    )

    # Отдельная аудит-запись `DAILY_HEAD_ASSIGN` (категория уже была
    # в enum-е до 2.3.C — для аналитики кто и когда стал главой).
    await audit.record(
        AuditEntry(
            action=AuditAction.DAILY_HEAD_ASSIGN,
            actor_id=actor_tg_id,
            target_kind="clan",
            target_id=str(clan_id),
            before=None,
            after={
                "player_id": saved.player_id,
                "moscow_date": saved.moscow_date.isoformat(),
                "source": saved.source.value,
                "bonus_cm": saved.bonus_cm,
            },
            reason=f"daily_head_{saved.source.value}",
            idempotency_key=f"daily_head_assign:{clan_id}:{moscow_date.isoformat()}",
            occurred_at=saved.assigned_at,
        )
    )

    # Re-fetch игрока, чтобы UI показал длину с применённой прибавкой.
    saved_player = await players.get_by_id(player_id=saved.player_id)

    return DailyHeadResolved(
        assignment=saved,
        player=saved_player,
        was_new=True,
    )


__all__ = ["_resolve_or_create_assignment"]
