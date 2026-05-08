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
