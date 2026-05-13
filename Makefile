.PHONY: help install install-dev lint format typecheck test cov audit imports ci pre-commit smoke load-test clean

PY ?= python3

help:
	@echo "Доступные таргеты (Спринт 0.1, без рантайма):"
	@echo "  make install       — runtime-зависимости (pip install -e .)"
	@echo "  make install-dev   — runtime + dev (включая pre-commit)"
	@echo "  make lint          — ruff check"
	@echo "  make format        — ruff format"
	@echo "  make typecheck     — mypy --strict"
	@echo "  make imports       — import-linter (контракт слоёв)"
	@echo "  make test          — pytest + coverage"
	@echo "  make cov           — отчёт coverage (term + html)"
	@echo "  make audit         — pip-audit (CVE)"
	@echo "  make pre-commit    — pre-commit run --all-files"
	@echo "  make load-test     — load-тесты Прометея-FakeRedis (Спринт 4.1-J)"
	@echo "  make ci            — полный набор (lint + types + imports + test + audit)"

install:
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e .

install-dev:
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"
	pre-commit install

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy

imports:
	lint-imports

test:
	pytest

cov:
	pytest --cov-report=term --cov-report=html
	@echo "HTML-отчёт: htmlcov/index.html"

audit:
	pip-audit --skip-editable

smoke:
	pytest -m smoke tests/smoke/ --no-cov

load-test:
	# Спринт 4.1-J: запуск load-сценариев на FakeRedis. `-o addopts=` обнуляет
	# дефолтные addopts из pyproject.toml (включая `-m "not load"` и xdist-
	# параллелизм — load-тесты профилируют latency, gather-конкуренция уже
	# внутри теста, xdist между файлами добавляет noise). --no-cov — на load-
	# тестах интересны p99-латенси, не покрытие. Параметризация через env-
	# vars `LOAD_OPS_COUNT` (default 2000) / `LOAD_P99_BUDGET_MS` (default 50).
	pytest -o addopts= -m load --no-cov tests/load/

pre-commit:
	pre-commit run --all-files

ci: lint typecheck imports test
	@echo "Локальный CI прошёл (без audit; см. CI workflow для CVE-проверки)."

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml \
	       build dist *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
