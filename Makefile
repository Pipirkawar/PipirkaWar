.PHONY: help install install-dev lint format typecheck test cov audit imports ci pre-commit clean

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

pre-commit:
	pre-commit run --all-files

ci: lint typecheck imports test
	@echo "Локальный CI прошёл (без audit; см. CI workflow для CVE-проверки)."

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml \
	       build dist *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
