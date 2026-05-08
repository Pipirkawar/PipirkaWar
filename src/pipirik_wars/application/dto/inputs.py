"""DTO входных данных use-case-ов.

Все валидации — pydantic-side; в use-case бизнес-логика уже работает
с проверенным объектом. На каждый отказ — конкретное поле и причина
(человекочитаемое сообщение через `bot/`-локализацию в Спринте 1.1+).
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# В геймплее tg_id всегда положительный; ботов и каналов мы здесь не валидируем.
PositiveTgId = int

# Telegram chat_kind для регистрации клана. Личные/каналы здесь не имеют
# смысла — клан = группа или супергруппа.
ClanChatKind = Literal["group", "supergroup"]


class _StrictBase(BaseModel):
    """Базовый DTO: запрещаем лишние поля и неявные конверсии."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
    )


class RegisterPlayerInput(_StrictBase):
    """Регистрация нового игрока через ЛС бота.

    `referrer_tg_id` — `tg_id` пригласившего; `None`, если пришли без рефки.
    """

    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id")
    username: str | None = Field(
        default=None,
        max_length=64,
        description="@username без @, может быть None",
    )
    locale: str = Field(
        default="ru",
        pattern=r"^[a-z]{2}(_[A-Z]{2})?$",
        description="ISO-код локали, например 'ru' или 'en_US'",
    )
    referrer_tg_id: PositiveTgId | None = Field(default=None, gt=0)


class RegisterClanInput(_StrictBase):
    """Регистрация клана при добавлении бота в группу.

    Use-case `RegisterClan` идемпотентен: если клан с таким `chat_id`
    уже существует и `frozen` — он размораживается; если `active` —
    no-op.
    """

    chat_id: int = Field(description="Telegram chat_id (отрицательный для групп)")
    chat_kind: ClanChatKind = Field(description='Тип чата: "group" или "supergroup".')
    title: str = Field(min_length=1, max_length=128)
    added_by_tg_id: PositiveTgId = Field(gt=0)


class MigrateClanChatIdInput(_StrictBase):
    """Миграция клана с group → supergroup (Telegram меняет `chat_id`).

    Передаётся из bot-handler-а, который ловит
    `message.migrate_to_chat_id`.
    """

    old_chat_id: int = Field(description="Прежний chat_id (group)")
    new_chat_id: int = Field(description="Новый chat_id (supergroup, обычно `-100…`)")
    new_chat_kind: ClanChatKind = Field(description='Тип нового чата (обычно "supergroup")')


class JoinClanInput(_StrictBase):
    """Добавление зарегистрированного игрока в клан-чат.

    Срабатывает при `chat_member`/`my_chat_member`, когда уже
    зарегистрированный (через ЛС) игрок виден в чате клана.
    """

    chat_id: int = Field(description="Telegram chat_id клана")
    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id игрока")


class FreezeClanInput(_StrictBase):
    """Заморозка клана при удалении бота из чата (Спринт 1.1.6)."""

    chat_id: int = Field(description="Telegram chat_id клана")
    reason: str = Field(
        default="bot_removed_from_chat",
        min_length=1,
        max_length=255,
    )


class GrantLengthInput(_StrictBase):
    """Админская выдача длины (обязательная причина → audit_log)."""

    target_tg_id: PositiveTgId = Field(gt=0)
    delta_cm: int = Field(description="Может быть отрицательным; ноль запрещён")
    reason: str = Field(min_length=3, max_length=512)
    idempotency_key: str = Field(min_length=8, max_length=255)


class StartForestRunInput(_StrictBase):
    """Старт похода в лес (Спринт 1.3.B).

    Игрок идентифицируется `tg_id`, как и во всех остальных входных
    DTO. Внутренний `player.id` use-case достанет через
    `IPlayerRepository.get_by_tg_id` — это даёт единый внешний контракт
    для bot-handler-ов, которые видят только Telegram-id.
    """

    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id игрока")


class FinishForestRunInput(_StrictBase):
    """Финиш похода в лес (Спринт 1.3.C).

    На вход — `run_id` записи `forest_runs`. Источник вызова —
    APScheduler-job, который Запланировал `StartForestRun` на `ends_at`.
    """

    run_id: int = Field(gt=0, description="forest_runs.id")


class StartMountainRunInput(_StrictBase):
    """Старт похода в горы (Спринт 3.1-B, ГДД §8).

    Аналогично `StartForestRunInput`: bot-handler видит игрока по `tg_id`,
    use-case резолвит `player.id` через `IPlayerRepository.get_by_tg_id`.
    """

    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id игрока")


class FinishMountainRunInput(_StrictBase):
    """Финиш похода в горы (Спринт 3.1-B).

    На вход — `run_id` записи `mountain_runs`. Источник вызова —
    APScheduler-job, запланированный `StartMountainRun` на `ends_at`.
    """

    run_id: int = Field(gt=0, description="mountain_runs.id")


class StartDungeonRunInput(_StrictBase):
    """Старт похода в данжон (Спринт 3.1-B, ГДД §8). Зеркалит горный."""

    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id игрока")


class FinishDungeonRunInput(_StrictBase):
    """Финиш похода в данжон (Спринт 3.1-B). Зеркалит горный."""

    run_id: int = Field(gt=0, description="dungeon_runs.id")


class ApplyForestNameDropInput(_StrictBase):
    """Применить выпавшее в лесу имя (Спринт 1.3.D, ГДД §2.5 / §8.2).

    Используется кнопкой «Заменить» на сообщении «вернулся из леса»,
    когда у игрока уже было имя и `FinishForestRun` оставил `NameDrop`
    без auto-apply. Use-case `ApplyForestNameDrop` делает фактическую
    замену с аудитом.

    `tg_id` сверяется с `forest_runs.player_id` через
    `IPlayerRepository.get_by_tg_id`: чужой пользователь не может
    применить чужой дроп.
    """

    run_id: int = Field(gt=0, description="forest_runs.id")
    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id игрока")


class UpgradeThicknessInput(_StrictBase):
    """Прокачка уровня толщины (Спринт 1.4.A, ГДД §3.2).

    Use-case `UpgradeThickness` сам считает стоимость по
    `balance.yaml::thickness.cost_*`, делает проверку правила 20 см
    через `progression.require_spend(THICKNESS_UPGRADE)` и поднимает
    `player.thickness` на 1.

    `expected_cost_cm` — опциональный «контракт» от UI: если он отличается
    от свежепосчитанной стоимости, use-case бросает `ConcurrencyError`.
    Это защита от ситуации «balance.yaml перегружен между показом
    подтверждения и нажатием Подтвердить» (см. Спринт 1.4.B при горячей
    перезагрузке баланса). `None` — пропустить проверку.
    """

    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id игрока")
    expected_cost_cm: int | None = Field(
        default=None,
        gt=0,
        description="Стоимость, которую UI показал пользователю; для защиты от race",
    )


class ChallengeDuelInput(_StrictBase):
    """Создание PvP-вызова 1×1 (Спринт 2.1.D, ГДД §7.1).

    `mode` — режим вызова из ГДД §7.1:

    * `chat_only` — только в чате клана (адресный, требует `challenged_tg_id`);
    * `chat_then_global` — сначала в чате клана, через 3 минуты «уплывает»
      в глобальное лобби (адресный на старте; перевод в `GLOBAL_ONLY`
      делает фоновый use-case 2.1.F);
    * `global_only` — сразу в глобальное лобби (без `challenged_tg_id`).

    `challenged_tg_id` обязателен для `chat_only` / `chat_then_global` и
    запрещён для `global_only` (доменный валидатор `Duel.create_challenge`
    дублирует это, но валидируем рано — до загрузки игроков).
    """

    challenger_tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id игрока, бросающего вызов",
    )
    challenged_tg_id: PositiveTgId | None = Field(
        default=None,
        gt=0,
        description="Telegram user_id адресата (None для global_only)",
    )
    mode: Literal["chat_only", "chat_then_global", "global_only"] = Field(
        description="Режим вызова (см. ГДД §7.1)",
    )

    @model_validator(mode="after")
    def _validate_mode_consistency(self) -> Self:
        if self.mode == "global_only" and self.challenged_tg_id is not None:
            raise ValueError(
                "challenged_tg_id must be None for mode='global_only'",
            )
        if self.mode != "global_only" and self.challenged_tg_id is None:
            raise ValueError(
                f"challenged_tg_id is required for mode={self.mode!r}",
            )
        return self


class AcceptDuelInput(_StrictBase):
    """Приём PvP-вызова (Спринт 2.1.D).

    `tg_id` сверяется с `Duel.challenged_id` (для адресных режимов) или
    становится новым `challenged_id` (для `GLOBAL_ONLY` — кто первым
    нажал «принять», тот и стал оппонентом).
    """

    duel_id: int = Field(gt=0, description="pvp_duels.id")
    tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id принимающего вызов",
    )


class CancelDuelInput(_StrictBase):
    """Отмена PvP-вызова до его принятия (Спринт 2.1.D).

    Отменить может только `challenger`. После принятия (`IN_PROGRESS`)
    отмена запрещена — `Duel.cancel` бросит `InvalidDuelStateError`.
    """

    duel_id: int = Field(gt=0, description="pvp_duels.id")
    tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id игрока, отменяющего вызов",
    )


class SubmitMoveInput(_StrictBase):
    """Отправка хода (атака+блок) в активной дуэли (Спринт 2.1.D).

    Use-case `SubmitMove` сам решает, нужно ли авторазрешать раунд (если
    оба выбора получены) и/или применить ±длины (если это последний раунд).
    """

    duel_id: int = Field(gt=0, description="pvp_duels.id")
    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id ходящего")
    attack: Literal["high", "mid", "low"] = Field(
        description="Куда бьёт игрок",
    )
    block: Literal["high", "mid", "low"] = Field(
        description="Какую зону защищает",
    )


class ResolveAfkRoundInput(_StrictBase):
    """AFK-фоллбэк раунда (Спринт 2.1.D, ГДД §7.1).

    Шедулер раунд-таймера (Спринт 2.1.G) дёргает use-case по истечении
    30–60 секунд: за каждого молчаливого игрока выбирается случайная
    атака+блок через `IRandom`, раунд авторазрешается. Если после
    этого дуэль завершена — применяются ±длины (как в `SubmitMove`).
    """

    duel_id: int = Field(gt=0, description="pvp_duels.id")
    round_num: int = Field(
        gt=0,
        description="Номер раунда, по которому истёк таймер",
    )


class InvokeOracleInput(_StrictBase):
    """Вызов `/oracle` (Спринт 1.4.B, ГДД §11).

    Локаль определяется `LocaleMiddleware` и пробрасывается до
    use-case-а; `IOracleTemplateProvider` подтянет каталог шаблонов
    нужного языка. Кулдаун (1 раз в сутки по Москве) считается на
    стороне use-case-а через `IClock.moscow_date()` и
    `IOracleHistoryRepository`.
    """

    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id игрока")
    locale: str = Field(
        default="ru",
        pattern=r"^[a-z]{2}(_[A-Z]{2})?$",
        description="Локаль каталога предсказаний (например, 'ru' или 'en')",
    )


class EnqueueGlobalDuelInput(_StrictBase):
    """Постановка дуэли в глобальную FIFO-очередь (Спринт 2.1.F.2)."""

    duel_id: int = Field(gt=0, description="pvp_duels.id")


class MatchFromLobbyInput(_StrictBase):
    """Пикап дуэли из глобального лобби (Спринт 2.1.F.2).

    Вызывается из `/duel_global`-handler-а. `accepter_tg_id` — Telegram
    user_id игрока, который нажал «Принять из глобал-пула».
    """

    accepter_tg_id: PositiveTgId = Field(
        gt=0, description="Telegram user_id игрока, принимающего из лобби"
    )


class EscalateChatToGlobalInput(_StrictBase):
    """Job-эскалации `CHAT_THEN_GLOBAL → GLOBAL_ONLY` (Спринт 2.1.F.2).

    Запускается планировщиком через
    `pvp.duel_1v1.chat_to_global_promotion_minutes` после создания
    chat-вызова. NO-OP, если дуэль уже принята/отменена.
    """

    duel_id: int = Field(gt=0, description="pvp_duels.id")


class StartMassDuelInput(_StrictBase):
    """Старт массового PvP-боя клан×клан (Спринт 2.2.E, ГДД §7.2 / 2.2.2).

    `attacker_chat_id` — `chat_id` клана-атакующего (тот, у кого
    инициатор нажал кнопку/команду в чате клана). `defender_chat_id` —
    `chat_id` клана-защитника. Use-case `StartMassDuel`:

    1. Резолвит оба клана по `chat_id` (`ClanRepository`); оба должны
       быть `active`.
    2. Запрашивает roster обеих сторон (`IClanMembershipRepository.list_by_clan`).
    3. Игроки в обоих кланах → пропускаются (ГДД §7.2 / 2.2.3).
    4. Каждый участник проходит eligibility-фильтр: `length_cm ≥
       balance.pvp.mass_duel.min_length_cm` и `thickness_level ≥
       balance.pvp.mass_duel.min_thickness_level` и `status == ACTIVE`.
    5. Если у любой стороны нет eligible-участников →
       `MassDuelNoParticipantsError`.
    6. Cooldown: `find_most_recent_for_clan` для каждого из двух
       кланов; если у любого клана был mass-duel за последние
       `balance.pvp.mass_duel.cooldown_hours` → `MassDuelCooldownError`.
    7. Берёт activity-lock на каждого eligible-участника.
    8. Создаёт `MassDuel.create_battle(...)` и `IMassDuelRepository.add(...)`.
    9. Audit `PVP_MASS_DUEL_CREATED`.
    """

    initiator_tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id игрока, инициировавшего атаку",
    )
    attacker_chat_id: int = Field(
        description="Telegram chat_id клана-атакующего",
    )
    defender_chat_id: int = Field(
        description="Telegram chat_id клана-защитника",
    )

    @model_validator(mode="after")
    def _validate_clans_differ(self) -> Self:
        if self.attacker_chat_id == self.defender_chat_id:
            raise ValueError(
                "attacker_chat_id and defender_chat_id must differ",
            )
        return self


class SubmitMassMoveInput(_StrictBase):
    """Отправка хода (атака+блок) в активном массовом бое (Спринт 2.2.E).

    Один игрок отправляет одну атаку и один блок. Если этим вызовом
    все участники отправили выборы — use-case остаётся в
    `IN_PROGRESS` (не резолвит сам, резолв делается отдельно через
    `ResolveMassDuel` или `ForceResolveMassDuel` шедулером).
    """

    duel_id: int = Field(gt=0, description="pvp_mass_duels.id")
    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id ходящего")
    attack: Literal["high", "mid", "low"] = Field(
        description="Куда бьёт игрок",
    )
    block: Literal["high", "mid", "low"] = Field(
        description="Какую зону защищает",
    )


class ResolveMassDuelInput(_StrictBase):
    """Финальный резолв массового боя (Спринт 2.2.E).

    Вызывается, когда все участники отправили выборы. Use-case:
    1. Загружает `MassDuel`. Нет — `MassDuelNotFoundError`.
    2. `MassDuel.resolve(random=..., now=...)` — доменный мутатор.
       Если кто-то ещё не отправил — `MassDuelNotReadyError`.
    3. Сохраняет агрегат с COMPLETED-статусом + damage_entries.
    4. Применяет ±длины ко всем участникам через
       `apply_mass_duel_outcome`.
    5. Снимает activity-locks всех участников.
    6. Audit `PVP_MASS_DUEL_COMPLETED`.
    """

    duel_id: int = Field(gt=0, description="pvp_mass_duels.id")


class ForceResolveMassDuelInput(_StrictBase):
    """AFK-фоллбэк массового боя (Спринт 2.2.E, ГДД §7.2).

    Вызывается шедулером (Спринт 2.2.F) по истечении round-таймера
    массового боя: за каждого молчаливого участника выбирается
    случайная атака+блок через `IRandom`, после чего бой резолвится.
    Если все уже отправили — `NoMissingMassMovesError` (use-case
    конвертит в no-op для идемпотентности).
    """

    duel_id: int = Field(gt=0, description="pvp_mass_duels.id")


class CancelMassDuelInput(_StrictBase):
    """Отмена активного массового боя (Спринт 2.2.E).

    Используется только для административных вмешательств (например,
    деградация ростера, abort через админ-команду). После `COMPLETED`
    отмена запрещена. Идемпотентна: повторная отмена уже отменённого
    боя — no-op.
    """

    duel_id: int = Field(gt=0, description="pvp_mass_duels.id")
    reason: str = Field(
        default="admin_cancel",
        max_length=64,
        description="Короткая причина отмены (для audit-лога)",
    )


class ExpireLobbyEntryInput(_StrictBase):
    """Job-истечения TTL глобального лобби (Спринт 2.1.F.2).

    Запускается планировщиком через `pvp.duel_1v1.global_lobby_ttl_minutes`
    после попадания дуэли в лобби. NO-OP, если уже не в лобби (принят
    другим игроком или отменён).
    """

    duel_id: int = Field(gt=0, description="pvp_duels.id")


class RequestDailyHeadInput(_StrictBase):
    """Запрос «Главы клана дня» из bot-handler-а (Спринт 2.3.C).

    Игрок жмёт кнопку «🎲 Назначить главу дня» или вводит `/clan_head`
    в клан-чате. Use-case резолвит клан по `chat_id`, проверяет
    `is_frozen`, и зовёт `DailyHeadService.assign_or_get(...,
    source=BUTTON)`. Идемпотентен по `(clan_id, moscow_date)` —
    повторный запрос в те же сутки вернёт уже-назначенную главу
    (этот же `Assignment`, без новых side-effects).

    `chat_id` — Telegram chat_id клан-чата (отрицательный для групп);
    нужен для резолва клана. `actor_tg_id` идёт в `audit_log.actor_id`,
    чтобы было видно, кто триггернул запись (для аналитики и расследований).
    """

    chat_id: int = Field(
        description="Telegram chat_id клан-чата (отрицательный для групп)",
    )
    actor_tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id игрока, нажавшего кнопку",
    )


class RunDailyHeadCronInput(_StrictBase):
    """Cron-триггер назначения «Главы клана дня» (Спринт 2.3.C).

    APScheduler в `random_offset(0..24h)`-час с 00:00 МСК зовёт этот
    use-case на каждый `clan_id` (Спринт 2.3.F). Use-case идемпотентен
    по `(clan_id, moscow_date)` — если глава уже назначен (например,
    кнопка сработала раньше), cron вернёт без повторного присвоения.
    """

    clan_id: int = Field(gt=0, description="Внутренний clans.id")


class RecordPlayerActivityInput(_StrictBase):
    """Запись активности игрока в `daily_active` (Спринт 2.3.F.1).

    Зовётся middleware-ом `DailyActivityMiddleware` на каждое входящее
    Telegram-сообщение от пользователя в групповом / супергрупповом
    чате. Use-case делает lookup игрока по `tg_user_id` (если игрок
    не зарегистрирован — no-op без ошибки) и UPSERT в `daily_active`
    по PK `(moscow_date, user_id)`.

    `tg_user_id` — Telegram user_id отправителя сообщения; реальный
    `users.id` (DB primary key) резолвится use-case-ом.
    """

    tg_user_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id игрока, проявившего активность",
    )


class RegisterReferralInput(_StrictBase):
    """Регистрация реферальной связи (Спринт 2.4.C, ГДД §13.1).

    Зовётся `/start`-handler-ом сразу **после** успешного `RegisterPlayer`,
    если в payload-е был `start=ref_<id>`. `referrer_tg_id` извлекается
    из payload-а; `referred_tg_id` — это сам новичок.

    Use-case `RegisterReferral` валидирует:
    - `referrer_tg_id != referred_tg_id` (само-реферал → ошибка);
    - реферер существует в `users` (иначе тихий no-op);
    - игрок ещё не имеет реферальной записи (UNIQUE по `referred_id`);
    - и затем создаёт запись в `referrals` (без начисления длины).

    Начисление signup-бонуса (+5 см новичку, +1 см рефереру) — отдельный
    use-case `GrantReferralSignupBonus`, который handler зовёт сразу
    после `RegisterReferral`. Разделение нужно, чтобы failure начисления
    не откатил саму реферальную связь (или наоборот).
    """

    referrer_tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id пригласившего (из start=ref_<id>)",
    )
    referred_tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id новичка (только что прошедший RegisterPlayer)",
    )

    @model_validator(mode="after")
    def _no_self_referral(self) -> Self:
        if self.referrer_tg_id == self.referred_tg_id:
            raise ValueError(
                f"referrer_tg_id ({self.referrer_tg_id}) "
                f"must differ from referred_tg_id ({self.referred_tg_id})"
            )
        return self


class GrantReferralSignupBonusInput(_StrictBase):
    """Начисление signup-бонуса по реферальной связи (Спринт 2.4.C, ГДД §13.1).

    Зовётся `/start`-handler-ом **после** `RegisterReferral`. Use-case
    `GrantReferralSignupBonus` идемпотентен по `signup_granted_at`:
    повторный вызов на уже-обработанной записи бросает
    `SignupBonusAlreadyGrantedError` (handler swallow-ит в no-op).

    Бонусы из `balance.referral.on_signup`:
    - `newbie_bonus_cm` см → новичку (`source=REFERRAL_SIGNUP`);
    - `referrer_bonus_cm` см → рефереру (`source=REFERRAL_SIGNUP`).

    Идемпотентность через `IIdempotencyKey`-ключи (namespace `add_length`):
    - `add_length:referral:signup:newbie:{referred_id}`;
    - `add_length:referral:signup:referrer:{referrer_id}:{referred_id}`.

    Все начисления — внутри одной транзакции через `ILengthGranter`,
    audit `LENGTH_GRANT` с `source=REFERRAL_SIGNUP` пишется автоматически.
    """

    referred_tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id новичка, которому начисляем signup-бонус",
    )


class GrantReferralThicknessMilestoneInput(_StrictBase):
    """Начисление milestone-бонуса по достижению толщины (Спринт 2.4.C, ГДД §13.1).

    Зовётся handler-ом `/upgrade_thickness` (Спринт 2.4.D) **после**
    успешного апгрейда толщины — но только если новый уровень совпадает
    с одним из `balance.referral.on_thickness_milestones`. Use-case
    проверяет:
    - реферальная запись существует (no-op если игрока никто не рефнул);
    - `last_milestone_thickness < new_thickness_level` (no-op иначе —
      `MilestoneAlreadyGrantedError`).

    Бонус начисляется **рефереру** через `ILengthGranter` с
    `source=REFERRAL_THICKNESS`. Идемпотентность через ключ
    `add_length:referral:thickness:{thickness}:{referrer_id}:{referred_id}`.
    """

    referred_tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id игрока, достигшего нового уровня толщины",
    )
    new_thickness_level: int = Field(
        ge=1,
        description="Новый уровень толщины (после успешного апгрейда)",
    )


class RunWeeklyClanReferralSummaryInput(_StrictBase):
    """Cron-триггер еженедельной сводки рефералов клана (Спринт 2.4.E, ГДД §13.3).

    APScheduler в воскресенье 18:00 UTC зовёт use-case на каждый
    `clan_id`. Use-case идемпотентен в смысле «нет побочных эффектов
    в БД»: только читает агрегаты и шлёт сообщение через notifier.
    """

    clan_id: int = Field(gt=0, description="Внутренний clans.id")


# ── Спринт 3.2-B (караваны, ГДД §9) ──


class CreateCaravanInput(_StrictBase):
    """Создание каравана из чата клана-отправителя (Спринт 3.2-B, ГДД §9.2).

    Игрок-инициатор зовёт `/caravan_create <receiver_chat_id> <contribution>`
    из чата своего клана. Use-case `CreateCaravan` резолвит оба клана
    по `chat_id`, валидирует условия (ГДД §9.1/§9.2):

    - Игрок состоит в клане-отправителе и его роль = leader (создавать
      может только лидер клана) — на уровне use-case проверяется через
      `IClanMembershipRepository.get_by_player`.
    - `thickness.level >= caravans.min_thickness_level_leader` (по ГДД =7).
    - `length.cm - contribution_cm >= caravans.min_length_after_contribution_cm`
      (по ГДД =20: «правило 20 см после взноса»).
    - Кулдаун клана-отправителя: с момента старта последнего каравана
      прошло `>= caravans.clan_cooldown_hours` часов (ГДД §9.3 = 12 ч).
    - У игрока нет другого активного `activity_lock` (правило одной
      активности).

    `sender_chat_id` — `chat_id` клана-отправителя (тот чат, где игрок
    нажал кнопку / ввёл команду). `receiver_chat_id` — чат клана-получателя
    (передан явно, валидатор не пускает совпадение).
    """

    initiator_tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id игрока, создающего караван (лидер клана)",
    )
    sender_chat_id: int = Field(
        description="Telegram chat_id клана-отправителя (чат, из которого зовут)",
    )
    receiver_chat_id: int = Field(
        description="Telegram chat_id клана-получателя",
    )
    contribution_cm: int = Field(
        gt=0,
        description="Вклад лидера в караван в см (целое > 0)",
    )

    @model_validator(mode="after")
    def _validate_clans_differ(self) -> Self:
        if self.sender_chat_id == self.receiver_chat_id:
            raise ValueError(
                "sender_chat_id and receiver_chat_id must differ",
            )
        return self


class JoinCaravanLobbyInput(_StrictBase):
    """Вступление игрока в лобби каравана (Спринт 3.2-B, ГДД §9.4).

    Игрок жмёт кнопку «Вступить как <role>» под объявлением каравана.
    Use-case `JoinCaravanLobby`:

    - Резолвит караван по `caravan_id`, проверяет `status == LOBBY`.
    - Резолвит игрока по `tg_id`.
    - Валидирует роль (ГДД §9.4) — таблица 5 кейсов двойного членства
      (см. `CaravanRoleConflictError`):
        * `CARAVANEER` — игрок должен быть в `sender_clan` (двойной
          член обоих кланов **может** выбрать `CARAVANEER`);
        * `DEFENDER` — игрок должен быть в `receiver_clan` (двойной
          член тоже может выбрать `DEFENDER`);
        * `RAIDER` — игрок не должен быть **ни в одном** из двух кланов.
    - Длинные требования (ГДД §9.2):
        * у `CARAVANEER` `length - contribution_cm >= 20 см`;
        * у `DEFENDER`/`RAIDER` `length >= 20 см`;
    - Capacity (ГДД §9.5):
        * `RAIDER` ≤ ×4 от количества `CARAVANEER` (вкл. лидера);
        * `DEFENDER` ≤ ×2 от количества `CARAVANEER` (вкл. лидера).
    - Берёт `activity_lock(player, CARAVAN, ttl=lobby+battle минут)`.
    - Сохраняет `CaravanParticipant` (UNIQUE (caravan_id, player_id)).

    `contribution_cm` обязателен только для `CARAVANEER`-роли;
    для `DEFENDER`/`RAIDER` он должен быть `None`.
    """

    tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id вступающего игрока",
    )
    caravan_id: int = Field(gt=0, description="caravans.id")
    role: Literal["caravaneer", "defender", "raider"] = Field(
        description="Запрошенная роль (см. ГДД §9.4)",
    )
    contribution_cm: int | None = Field(
        default=None,
        gt=0,
        description="Вклад в см (только для caravaneer; иначе None)",
    )

    @model_validator(mode="after")
    def _validate_contribution_role_consistency(self) -> Self:
        if self.role == "caravaneer" and self.contribution_cm is None:
            raise ValueError(
                "contribution_cm is required for role='caravaneer'",
            )
        if self.role != "caravaneer" and self.contribution_cm is not None:
            raise ValueError(
                f"contribution_cm must be None for role={self.role!r}",
            )
        return self


class LeaveCaravanLobbyInput(_StrictBase):
    """Выход игрока из лобби каравана (Спринт 3.2-B, ГДД §9.3).

    Игрок жмёт «Выйти» в лобби. Use-case `LeaveCaravanLobby`:

    - Резолвит караван (`status == LOBBY`).
    - Удаляет `CaravanParticipant(caravan_id, player_id)`.
    - Снимает `activity_lock(player, CARAVAN)`.
    - НЕ возвращает `contribution_cm` обратно в длину игрока: длина
      и так не списывалась на этапе вступления (списание в момент
      `LOBBY → IN_BATTLE` в Спринте 3.2-C).
    - Лидер выйти не может — на это есть отдельный use-case
      `CancelCaravanLobby` в 3.2-C (отменяет весь караван).
    """

    tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id выходящего игрока",
    )
    caravan_id: int = Field(gt=0, description="caravans.id")


class CloseCaravanLobbyInput(_StrictBase):
    """Закрытие лобби каравана по таймеру (Спринт 3.2-B, ГДД §9.3).

    Вызывается APScheduler-job-ом `caravan_lobby_close` через
    `caravans.lobby_minutes` (=20) после `CreateCaravan`. Use-case
    переводит караван `LOBBY → IN_BATTLE` идемпотентно
    (повторный вызов на уже-`IN_BATTLE`/`FINISHED`/`CANCELLED` —
    no-op с `was_already_closed=True`).

    Сам resolve боя (применение исходов, награды) — отдельный
    use-case `FinishCaravanBattle` в Спринте 3.2-C; здесь только
    переход статуса + audit `CARAVAN_LOBBY_CLOSED`. Постановку
    `caravan_battle_finish`-job-а на `battle_ends_at` оставляем
    тоже на 3.2-C.
    """

    caravan_id: int = Field(gt=0, description="caravans.id")


class FinishCaravanBattleInput(_StrictBase):
    """Завершение боя каравана по таймеру (Спринт 3.2-C, ГДД §9.5–§9.6).

    Вызывается APScheduler-job-ом `caravan_battle_finish` в
    `caravan.battle_ends_at` (через `caravans.battle_minutes` после
    закрытия лобби). Use-case детерминистично резолвит бой по
    `caravan.random_seed` (через `resolve_caravan_battle`), применяет
    per-player длины + клан-бонус +1 см к участникам обоих кланов
    + `Title.ATAMAN` случайному рейдеру при их победе, и переводит
    караван `IN_BATTLE → FINISHED`.

    Идемпотентность — через сам статус: повторный вызов на
    `FINISHED`/`CANCELLED` — NO-OP с `was_already_finished=True`,
    без повторного применения наград и без новых audit-записей.
    """

    caravan_id: int = Field(gt=0, description="caravans.id")


class CancelCaravanInput(_StrictBase):
    """Отмена каравана лидером из `LOBBY` (Спринт 3.2-D, ГДД §9.3).

    Лидер каравана (создатель, `caravan.leader_player_id`) жмёт
    «Отменить караван» в лобби. Use-case `CancelCaravan`:

    - Резолвит караван (`status == LOBBY`); из `IN_BATTLE`/`FINISHED`
      бросает `InvalidCaravanStateError`. Из уже-`CANCELLED` —
      идемпотентный no-op (`was_already_cancelled=True`).
    - Сверяет, что `tg_id` == игрок-лидер каравана; иначе
      `CaravanRoleConflictError(attempted_role="cancel")`.
    - Переводит караван `LOBBY → CANCELLED` (`Caravan.mark_cancelled`).
    - Снимает `activity_lock(player, CARAVAN)` для всех участников
      (включая лидера). NO-OP, если лок уже снят.
    - Отзывает запланированные APScheduler-job-ы:
      `cancel_caravan_lobby_close(caravan_id)` (battle-finish-job ещё
      не был запланирован — его ставит `CloseCaravanLobby` при
      переходе `LOBBY → IN_BATTLE`).
    - Audit `CARAVAN_CANCELLED` с idempotency-key
      `caravan_cancelled:{caravan_id}`.

    Длины игроков НЕ восстанавливаются — на этапе лобби они и не
    списывались (списание только в `FinishCaravanBattle`,
    Спринт 3.2-C).
    """

    caravan_id: int = Field(gt=0, description="caravans.id")
    tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id игрока-инициатора отмены (должен быть лидером)",
    )


# ── Спринт 3.3-B (рейд-боссы, ГДД §10) ──


class SummonBossInput(_StrictBase):
    """Призыв рейд-босса игроком (Спринт 3.3-B, ГДД §10.1 — §10.3).

    Игрок-саммонер инициирует рейд через `/boss`-команду (handler — 3.3-D).
    Use-case `SummonBoss` (3.3-B):

    - Резолвит игрока по `summoner_tg_id` (`PlayerNotFoundError` /
      `PlayerFrozenError` для не-`ACTIVE`).
    - Валидирует требования к саммонеру (ГДД §10.1):
        * `thickness.level >= bosses.min_thickness_level_summoner` (=9);
        * `length.cm >= bosses.min_length_cm` (=20).
    - Проверяет глобальный 4-часовой кулдаун (ГДД §10.1: «1 раз в 4 часа
      (глобальный)») через `IBossFightRepository.get_last_global_started_at`
      → `BossSummonOnGlobalCooldownError` с остатком в секундах. По решению
      cyan91 на старте 3.3-A — кулдаун **на весь сервер**, не per-clan и
      не per-player; CANCELLED-бои тоже «съедают» кулдаун.
    - Берёт `activity_lock(player, BOSS_FIGHT, ttl=lobby_minutes)` для
      саммонера; `LockAlreadyHeldError` → `AlreadyInBossFightError`.
    - Выбирает `boss_player_id` случайно из топ-N по длине через
      `IPlayerRepository.list_top_by_length(limit=bosses.top_n_pool)`,
      исключая саммонера. Пустой пул → `BossPlayerPoolEmptyError`.
    - Создаёт `BossFight.starting(...)` (`status=LOBBY`,
      `current_boss_length_cm=initial_boss_length_cm`).
    - Создаёт первого `BossParticipant.raider(is_summoner=True, ...)`
      (саммонер — всегда первый рейдер; ГДД §10.3 «минимум 1 рейдер»).
    - Шедулит `boss_lobby_close(boss_fight_id, run_at=lobby_ends_at)`
      на `started_at + bosses.lobby_minutes`.
    - Audit `BOSS_FIGHT_SUMMONED` (idempotency-key
      `boss_fight_summoned:{boss_fight_id}`).

    Поле `chat_id` не требуется на уровне use-case — рейд глобальный,
    презентация (в каком чате опубликовать «вступить»-кнопку) — забота
    bot-handler-а в Спринте 3.3-D.
    """

    summoner_tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id игрока-саммонера, призывающего босса",
    )


class JoinBossLobbyInput(_StrictBase):
    """Вступление рейдера в лобби рейд-боя (Спринт 3.3-B, ГДД §10.1, §10.3).

    Игрок жмёт кнопку «Вступить в рейд» под объявлением вызова. Use-case
    `JoinBossLobby`:

    - Резолвит рейд-бой (`IBossFightRepository.get_by_id`); не найден →
      `BossFightNotFoundError`. `status != LOBBY` → `BossFightLobbyClosedError`.
    - Резолвит игрока по `tg_id`; не найден → `PlayerNotFoundError`,
      `FROZEN`/`BANNED` → `PlayerFrozenError`.
    - Валидирует требования к рейдеру (ГДД §10.1):
        * `thickness.level >= bosses.min_thickness_level_raider` (=4);
        * `length.cm >= bosses.min_length_cm` (=20).
    - Проверяет, что игрок — не саммонер (он уже вступил в `SummonBoss`)
      и не сам босс (босс не может быть рейдером в собственном бою) —
      `NotInBossFightError`-семантически некорректно бросать; используем
      `AlreadyInBossFightError(player_id=...)` для саммонера и просто
      no-op-on-duplicate-семантику через `IBossParticipantRepository`-
      UNIQUE-индекс. Для босса — отдельный `CaravanRoleConflictError`-
      аналог; в 3.3-B — через `AlreadyInBossFightError` (бросает
      `_ensure_not_boss`). Конкретику смотри в use-case-е.
    - Берёт `activity_lock(player, BOSS_FIGHT, ttl)`; `LockAlreadyHeldError` →
      `AlreadyInBossFightError`.
    - Сохраняет `BossParticipant.raider(is_summoner=False, ...)` через
      `IBossParticipantRepository.add(...)`. БД-инвариант UNIQUE
      `(boss_fight_id, player_id)` гарантирует от повторного входа.
    - Audit `BOSS_RAIDER_JOINED` (idempotency-key
      `boss_raider_joined:{boss_fight_id}:{player_id}`).
    """

    tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id вступающего рейдера",
    )
    boss_fight_id: int = Field(gt=0, description="boss_fights.id")


class LeaveBossLobbyInput(_StrictBase):
    """Выход рейдера из лобби рейд-боя (Спринт 3.3-B, ГДД §10.3).

    Игрок жмёт «Выйти» в лобби. Use-case `LeaveBossLobby`:

    - Резолвит рейд-бой; не найден → `BossFightNotFoundError`.
      `status != LOBBY` → `BossFightLobbyClosedError` (после старта боя
      выход — это уже выбывание в раунде, не «выход из лобби»).
    - Резолвит игрока по `tg_id`.
    - Игрок должен быть участником этого боя — иначе
      `NotInBossFightError`. Саммонер выйти из лобби **может**:
      это эквивалентно отмене рейда (use-case переводит бой
      `LOBBY → CANCELLED` в той же транзакции, кулдаун не сбрасывается
      по решению cyan91 в 3.3-A — см. `domain/bosses/value_objects.py`).
      В 3.3-B саммонер-leave идёт по тому же пути, что и обычный
      рейдер-leave (просто удаляется participant + снимается lock).
      Если после ухода саммонера рейдеров больше нет, бот-handler в
      3.3-D отдельно вызовет `CancelBossFight` (use-case 3.3-C).
      В 3.3-B — saummoner-leave НЕ переводит бой в `CANCELLED`
      автоматически (этот use-case добавим в 3.3-C).
    - `IBossParticipantRepository.remove(boss_fight_id, player_id)`.
    - Снимает `activity_lock(player, BOSS_FIGHT)` (NO-OP, если лока нет).
    - Audit `BOSS_RAIDER_LEFT` (idempotency-key
      `boss_raider_left:{boss_fight_id}:{player_id}:{joined_at_iso}`).
    """

    tg_id: PositiveTgId = Field(
        gt=0,
        description="Telegram user_id выходящего рейдера",
    )
    boss_fight_id: int = Field(gt=0, description="boss_fights.id")


class CloseBossLobbyInput(_StrictBase):
    """Закрытие лобби рейд-боя по таймеру (Спринт 3.3-B, ГДД §10.3 → §10.4).

    Вызывается APScheduler-job-ом `boss_lobby_close` через
    `bosses.lobby_minutes` (=20) после `SummonBoss`. Use-case переводит
    рейд-бой `LOBBY → IN_BATTLE` идемпотентно (повторный вызов на уже
    `IN_BATTLE`/`FINISHED`/`CANCELLED` — no-op с `was_already_closed=True`).

    Сам resolve-боя (раунды, выбывание рейдеров, награды) — отдельные
    use-case-ы `RunBossRound` / `FinishBossFight` в Спринте 3.3-C; здесь
    только переход статуса + audit `BOSS_FIGHT_STARTED` + постановка
    `boss_round_tick`-job-а на первый раунд + `boss_fight_finish`-job-а
    как safety-net (на случай зависшего боя).
    """

    boss_fight_id: int = Field(gt=0, description="boss_fights.id")


# ── Спринт 3.3-C (рейд-боссы: бой, ГДД §10.4–§10.5) ──


class RunBossRoundInput(_StrictBase):
    """Резолв одного раунда рейд-боя (Спринт 3.3-C, ГДД §10.4).

    Вызывается APScheduler-job-ом `boss_round_tick` (первый — поставлен
    `CloseBossLobby` в момент `LOBBY → IN_BATTLE` в 3.3-D; последующие —
    самим `RunBossRound`-use-case-ом, если бой продолжается). Use-case:

    - Резолвит рейд-бой (`IBossFightRepository.get_by_id`); не найден →
      `BossFightNotFoundError`.
    - Идемпотентность по статусу: `FINISHED`/`CANCELLED` → no-op
      (`was_already_finished=True`), без аудита и шедула.
    - Не-`IN_BATTLE` (например, `LOBBY` — bug шедулера) →
      `InvalidBossFightStateError`.
    - Загружает всех живых рейдеров через
      `IBossParticipantRepository.list_by_boss_fight(...)`. Если их 0
      (corner-case: все выбыли в предыдущем раунде, но `mark_finished`
      ещё не успел стрельнуть) — выходит из боя через `mark_finished`
      без вызова resolve-сервиса (рейдеры проиграли — `FinishBossFight`
      в 3.3-C распределит «штрафные» длины).
    - Резолвит раунд через `boss_round_resolution.resolve_boss_round`
      (Спринт 3.3-C / C.1) с детерминистичным `SeededRandom`, seed
      которого — комбинация `boss_fight.random_seed` и `current_round`
      (это даёт независимо воспроизводимые результаты per-round).
    - Применяет `BossRoundResult`:
        * `boss_fight.with_boss_length(max(0, current - boss_damage_taken_cm))`;
        * удаление выбывших рейдеров (`participants.remove`) +
          `ActivityLockService.release` для каждого;
        * `boss_fight.with_round_advanced()` — инкремент счётчика;
        * `mark_finished` если `current_boss_length_cm < victory_threshold_cm`
          (рейдеры победили) или если после раунда все рейдеры выбыли
          (босс победил).
    - Записывает audit `BOSS_FIGHT_ROUND_RESOLVED` с idempotency-key
      `boss_fight_round_resolved:{boss_fight_id}:{round_number}`.
    - Если бой не закончен — шедулит следующий `boss_round_tick` на
      `now + bosses.round_max_seconds` через
      `IDelayedJobScheduler.schedule_boss_round_tick`. Если закончен —
      cancel-ит pending-tick и safety-net-finish (best-effort cleanup;
      реальный `FinishBossFight` шедулится отдельно из этого же
      use-case-а **в C.3** — пока что в C.2 это TODO, статус-переход в
      `FINISHED` записывается, но раздачу наград C.2 не делает).

    В C.2 саммонер-mode-стаб: всегда AFK (`is_summoner_online=False`),
    все ходы за рейдеров и босса генерирует `IRandom`-сервис. UI выбора
    блоков и ходов саммонера — Спринт 3.3-D.
    """

    boss_fight_id: int = Field(gt=0, description="boss_fights.id")


class FinishBossFightInput(_StrictBase):
    """Применение исхода рейд-боя и распределение наград (Спринт 3.3-C, ГДД §10.5–§10.6).

    Вызывается APScheduler-job-ом `boss_fight_finish` (safety-net,
    поставленный `CloseBossLobby` в момент `LOBBY → IN_BATTLE`), либо
    напрямую `RunBossRound`-use-case-ом сразу после раунда, который
    закрыл бой (HP босса < `victory_threshold_cm` или все рейдеры
    выбыли). Use-case `FinishBossFight`:

    - Резолвит рейд-бой (`IBossFightRepository.get_by_id`); не найден →
      `BossFightNotFoundError`.
    - Идемпотентность по статусу: если `FINISHED` уже был обработан
      `FinishBossFight`-ом ранее (определяется по аудит-записи
      `BOSS_REWARDS_GRANTED:{boss_fight_id}` — `idempotency_key`-CHECK
      в БД отсекает дубль), либо `CANCELLED` — no-op
      (`was_already_finished=True`), без аудита и без grant-ов.
      В C.3 идемпотентность реализована через сам факт `status=FINISHED`
      + наличие `BOSS_REWARDS_GRANTED`-записи: повторный вызов
      даёт UNIQUE-conflict в audit_log и откатывает транзакцию,
      эффективно превращая повторный финиш в no-op.
    - `LOBBY` (job не должен был сработать без перехода) →
      `InvalidBossFightStateError`.
    - `IN_BATTLE` (safety-net-job стрельнул, но раунды ещё идут — это
      «таймаут боя») — закрываем бой как поражение рейдеров.
    - Загружает живых рейдеров (`IBossParticipantRepository.list_by_boss_fight`).
      Если `current_boss_length_cm < bosses.victory_threshold_cm` —
      рейдеры победили (победа сохраняется даже при пустом списке
      рейдеров — это редкий corner-case "оба умерли в один раунд").
      Иначе — рейдеры проиграли.
    - **Победа рейдеров** (ГДД §10.5):
        * Каждый живой рейдер получает length-grant
          `+initial_boss_length_cm / N` см (N = число живых) через
          `ILengthGranter.grant(source=RAID_REWARD)` с idempotency-key
          `add_length:boss_fight_reward:{boss_fight_id}:{player_id}`.
        * Per-player ролл скроллов (regular + blessed, независимо)
          через `IRandom.bernoulli`; на каждый успех пишется audit
          `SCROLL_DROP` с idempotency-key
          `boss_scroll_drop:{boss_fight_id}:{player_id}:{scroll_kind}`.
          Скролл сейчас (3.3-C) **не** записывается в инвентарь —
          только audit (см. §6.3.1+ из `development_plan.md`); реальная
          инвентарная инфраструктура — Спринт 3.4 «Заточка предметов».
        * Босс получает refund-возврат своей длины **до уровня
          `victory_threshold_cm`**: его текущая `length` подтягивается
          вверх до `victory_threshold_cm`, чтобы он не остался на 9 см.
          Это прямой вызов метода `Player.with_length` + audit
          `LENGTH_GRANT`,
          не через `ILengthGranter` — refund к себе самому от себя
          самого, anti-cheat hardcap не применим.
    - **Поражение рейдеров** (ГДД §10.5):
        * Каждый живой рейдер теряет фиксированную сумму, накопленную
          им за раунды (`base_damage_cm` × число «отбитых блоков») —
          но по решению cyan91 на 3.3-C raider-loss-вычеты выносим
          в Спринт 3.3-D (вместе с UI «вы проиграли»). Здесь — только
          length-grant боссу (`+sum(length_at_join_cm)` всех живых на
          входе участников; реалистичный «он съел всех») через
          `ILengthGranter.grant(source=RAID_REWARD)` с idempotency-key
          `add_length:boss_loss_grant:{boss_fight_id}`.
    - Снимает `activity_lock(player, *)` для всех живых рейдеров +
      саммонера + босса (NO-OP, если уже снят/истёк).
    - `boss_fight.mark_finished(finished_at=now)`, сохраняет.
    - Cancel-ит pending-tick-job + safety-net-finish-job (best-effort).
    - Audit `BOSS_FIGHT_FINISHED` (idempotency-key
      `boss_fight_finished:{boss_fight_id}`) + `BOSS_REWARDS_GRANTED`
      (агрегаты — granted/loss/scroll-drops; idempotency-key
      `boss_rewards_granted:{boss_fight_id}`).

    Транзакционность: всё внутри `IUnitOfWork`. Любая ошибка откатывает
    все mutations + аудит — job-воркер ретраит позже, `idempotency_key`-и
    защитят от двойного применения.
    """

    boss_fight_id: int = Field(gt=0, description="boss_fights.id")
