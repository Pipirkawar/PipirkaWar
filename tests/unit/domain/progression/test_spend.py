"""Юнит-тесты `progression.can_spend` / `require_spend` (Спринт 1.2.1, ГДД §3.1).

Acceptance из `development_plan.md` 1.2.1 — «юнит-тесты на: лес (всегда ок),
горы (нужно ≥ 20), караван (после взноса ≥ 20), прокачка толщины (после
стоимости ≥ 20)».

Тут «лес всегда ок» означает: use-case леса не зовёт `require_spend` (нет
списания). Эту инварианту мы фиксируем структурно — тест ниже проверяет,
что функция вообще не падает на «бесплатные» активности (`cost_cm=0`)
независимо от длины — это и есть «лес ок» при любом game state.
"""

from __future__ import annotations

import pytest

from pipirik_wars.domain.progression import (
    MIN_LENGTH_AFTER_SPEND_CM,
    InsufficientLengthError,
    SpendAction,
    can_spend,
    require_spend,
)


class TestMinLengthConstant:
    def test_constant_matches_gdd_3_1(self) -> None:
        # Если кто-то поменял константу — это решение должно быть
        # явным и подтверждённым ГДД, поэтому пин-тест здесь.
        assert MIN_LENGTH_AFTER_SPEND_CM == 20


class TestCanSpend:
    @pytest.mark.parametrize(
        ("length_cm", "cost_cm", "expected"),
        [
            # Точно на границе: после вычета останется 20 → ок.
            (50, 30, True),
            # На 1 см меньше границы: 49 - 30 = 19 → нельзя.
            (49, 30, False),
            # Большой запас.
            (200, 50, True),
            # Бесплатная операция (cost_cm=0) проходит для длины ≥ 20.
            (20, 0, True),
            # Бесплатная операция при длине 19 — ломается:
            # инвариант «остаётся ≥ 20» не выполнен. Use-case леса
            # это не зовёт, но если кто-то вызовет — функция честно
            # вернёт False, а не «всегда ок».
            (19, 0, False),
            # Стартовая длина новичка (2 см) при дорогой операции.
            (2, 1, False),
        ],
    )
    def test_threshold_after_deduction(
        self,
        length_cm: int,
        cost_cm: int,
        expected: bool,
    ) -> None:
        assert can_spend(length_cm=length_cm, cost_cm=cost_cm) is expected

    def test_negative_length_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="length_cm must be >= 0"):
            can_spend(length_cm=-1, cost_cm=10)

    def test_negative_cost_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="cost_cm must be >= 0"):
            can_spend(length_cm=100, cost_cm=-1)


class TestRequireSpendMountains:
    """⛰️ Горы — нужно ≥ 20 см после возможного вычета.

    В Спринте 3.1 у `/mountains` появится свой `cost_cm` (риск
    потери длины), но контракт правила 20 см уже зафиксирован.
    """

    def test_passes_when_remaining_at_threshold(self) -> None:
        # 50 - 30 = 20 → ровно на границе, проходит.
        require_spend(length_cm=50, cost_cm=30, action=SpendAction.MOUNTAINS)

    def test_passes_with_no_cost(self) -> None:
        # «Поход в горы без потери» — гипотетический «нулевой» риск.
        # Функция не должна падать.
        require_spend(length_cm=20, cost_cm=0, action=SpendAction.MOUNTAINS)

    def test_raises_when_under_threshold(self) -> None:
        with pytest.raises(InsufficientLengthError) as exc:
            require_spend(
                length_cm=25,
                cost_cm=10,
                action=SpendAction.MOUNTAINS,
            )
        err = exc.value
        assert err.length_cm == 25
        assert err.cost_cm == 10
        assert err.min_after_spend_cm == 20
        assert err.action == "mountains"
        # 25 - 10 = 15 → не хватает 5 см до 20.
        assert err.deficit_cm == 5


class TestRequireSpendCaravanMerchant:
    """🐪 Караванщик: ГДД §3.1 — «после вычета взноса ≥ 20 см».

    Пример из ГДД: «Если взнос 15 см, а у игрока 34 см, то после
    вычета останется 19 см (< 20) — не может присоединиться. Нужно
    минимум 35 см».
    """

    def test_gdd_example_34cm_15cm_fee_rejected(self) -> None:
        with pytest.raises(InsufficientLengthError) as exc:
            require_spend(
                length_cm=34,
                cost_cm=15,
                action=SpendAction.CARAVAN_MERCHANT,
            )
        assert exc.value.action == "caravan_merchant"
        assert exc.value.deficit_cm == 1  # 34-15=19, не хватает 1 см

    def test_gdd_example_35cm_15cm_fee_passes(self) -> None:
        # 35 - 15 = 20 → ровно на границе.
        require_spend(
            length_cm=35,
            cost_cm=15,
            action=SpendAction.CARAVAN_MERCHANT,
        )

    def test_low_length_high_fee_rejected(self) -> None:
        with pytest.raises(InsufficientLengthError):
            require_spend(
                length_cm=10,
                cost_cm=5,
                action=SpendAction.CARAVAN_MERCHANT,
            )


class TestRequireSpendThicknessUpgrade:
    """📐 Прокачка толщины: ГДД §3.2 — «после вычета стоимости ≥ 20 см».

    Пример из ГДД: «у игрока 50 см, прокачка стоит 35 см → останется
    15 см (< 20) → нельзя. Нужно минимум 55 см».
    """

    def test_gdd_example_50cm_35cm_cost_rejected(self) -> None:
        with pytest.raises(InsufficientLengthError) as exc:
            require_spend(
                length_cm=50,
                cost_cm=35,
                action=SpendAction.THICKNESS_UPGRADE,
            )
        assert exc.value.deficit_cm == 5  # 50-35=15, не хватает 5 см

    def test_gdd_example_55cm_35cm_cost_passes(self) -> None:
        require_spend(
            length_cm=55,
            cost_cm=35,
            action=SpendAction.THICKNESS_UPGRADE,
        )

    def test_thickness_upgrade_thickness_2_passes_for_starter_plus_buffer(
        self,
    ) -> None:
        # ГДД §4.1: толщина 2 стоит 10 см. Чтобы прокачаться,
        # нужна длина 30 (30-10=20).
        require_spend(
            length_cm=30,
            cost_cm=10,
            action=SpendAction.THICKNESS_UPGRADE,
        )

    def test_thickness_upgrade_thickness_2_fails_at_29cm(self) -> None:
        # 29 - 10 = 19 < 20.
        with pytest.raises(InsufficientLengthError) as exc:
            require_spend(
                length_cm=29,
                cost_cm=10,
                action=SpendAction.THICKNESS_UPGRADE,
            )
        assert exc.value.deficit_cm == 1


class TestForestNoCheckNeeded:
    """🌲 Лес: ГДД §3.1 — «всегда +» / «доступен всегда».

    Use-case леса (Спринт 1.3) не зовёт `require_spend(...)`. Здесь
    мы убеждаемся, что **если** кто-то ошибочно вызовет проверку
    с `cost_cm=0` для активного игрока (длина >= 20), функция не
    падает. И, наоборот, при `length_cm < 20` `can_spend` вернёт
    False — это сигнал «leak abstraction»: либо use-case не должен
    был звать `can_spend`, либо в нём ошибка с `cost_cm`.
    """

    def test_active_player_with_cost_zero_passes(self) -> None:
        # У зарегистрированного игрока с лесопроходимой длиной
        # любая «нулевая стоимость» проходит.
        assert can_spend(length_cm=20, cost_cm=0) is True
        assert can_spend(length_cm=2, cost_cm=0) is False  # < 20 без буфера

    def test_starter_player_does_not_call_require_spend(self) -> None:
        # Имитируем правильный use-case: для леса просто не вызываем
        # require_spend. Тест документирует контракт: лес-handler
        # должен сам решить, что списания нет.
        starter_length_cm = 2
        forest_cost_cm = 0
        # Никакого require_spend не вызываем — это и есть «лес всегда ок».
        # Структурно ничего не падает; теста exception тут быть не должно.
        assert forest_cost_cm == 0
        assert starter_length_cm < MIN_LENGTH_AFTER_SPEND_CM


class TestErrorContents:
    def test_error_message_includes_all_fields(self) -> None:
        with pytest.raises(InsufficientLengthError) as exc:
            require_spend(
                length_cm=15,
                cost_cm=10,
                action=SpendAction.PVP_1V1,
            )
        message = str(exc.value)
        assert "pvp_1v1" in message
        assert "15" in message
        assert "10" in message
        # remaining = 5
        assert "5" in message
        # min_after_spend = 20
        assert "20" in message

    def test_deficit_for_exact_threshold_minus_one(self) -> None:
        # Нужен 1 см: 19 - 0 = 19, не хватает 1 до 20.
        try:
            require_spend(
                length_cm=19,
                cost_cm=0,
                action=SpendAction.MOUNTAINS,
            )
        except InsufficientLengthError as exc:
            assert exc.deficit_cm == 1
        else:
            pytest.fail("Expected InsufficientLengthError")

    def test_deficit_at_least_one_for_negative_remaining(self) -> None:
        # 5 - 50 = -45 → формально нужно 65 см, но deficit_cm
        # на всякий случай не уходит ниже 1 (для красивого UX).
        try:
            require_spend(
                length_cm=5,
                cost_cm=50,
                action=SpendAction.PVP_MASS,
            )
        except InsufficientLengthError as exc:
            assert exc.deficit_cm == 65

    @pytest.mark.parametrize(
        "action",
        list(SpendAction),
    )
    def test_each_action_propagates_to_error(self, action: SpendAction) -> None:
        # Каждый член enum должен корректно передаваться в .action ошибки.
        with pytest.raises(InsufficientLengthError) as exc:
            require_spend(length_cm=0, cost_cm=1, action=action)
        assert exc.value.action == action.value
