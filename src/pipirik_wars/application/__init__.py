"""Application-слой: use-cases (Application Services).

Тонкая оркестрация доменной логики. Каждый use-case = один сценарий
использования системы (RegisterPlayer, StartForestRun, AssignDailyHead, ...).

Может импортировать:
- domain/ — для работы с бизнес-логикой.

НЕ ИМЕЕТ права импортировать:
- infrastructure/ (только через порты — Protocol-интерфейсы из application/ports)
- bot/, admin/

Все внешние зависимости (БД, Telegram, платежи) — через Protocol/ABC,
конкретные реализации внедряются через DI в composition root.
"""
